# Khai báo công cụ biên dịch hoặc bộ dệt trong quy trình xây dựng AOP

## 1. Mục tiêu

Khi dùng **Aspect-Oriented Programming (AOP)**, khai báo một `aspect` hay `advice` trong mã nguồn chưa đủ để hành vi cắt ngang xuất hiện lúc chương trình chạy. Tùy kỹ thuật AOP, quy trình build phải **biên dịch aspect**, **dệt (weave) aspect vào những lớp mục tiêu**, hoặc **đóng gói bộ dệt để xử lý khi JVM nạp lớp**. Bài này giải thích cách chọn và khai báo các bước đó trong build, cách quản lý dependency, cách kiểm chứng file đầu ra và các lỗi cấu hình thường gặp.

Một cấu hình build đúng cần trả lời được:

1. **Ai thực thi biên dịch/dệt?** Ví dụ: trình biên dịch/weaver `ajc`, một tác vụ build tùy biến, plugin, hoặc Java agent.
2. **Đầu vào nằm ở đâu?** Mã Java, mã aspect, thư viện chứa aspect, các file `.class`/JAR đã biên dịch và các dependency liên quan.
3. **Dệt vào lúc nào?** Khi biên dịch, sau khi biên dịch, hay khi JVM nạp lớp.
4. **Đầu ra thực sự nào được chạy/phát hành?** Các lớp sau weaving, file JAR chứa chúng, hoặc ứng dụng nguyên bản kèm agent và cấu hình.
5. **Làm sao chứng minh advice đã được nối?** Thông báo `weave info`, smoke test, bytecode, và kiểm tra lệnh chạy.

Về bản chất, pointcut mô tả **những join point cần chọn**; compiler/weaver hoặc interceptor infrastructure quyết định **liệu hành vi đó được tích hợp vào luồng chạy hay không**. Một pointcut đúng nhưng khâu dệt không hoạt động vẫn có thể khiến advice hoàn toàn vắng mặt.

## 2. Phân loại kỹ thuật AOP và trách nhiệm của build

| Cơ chế | Khi nào tích hợp advice? | Điều cần khai báo trong build/triển khai |
| --- | --- | --- |
| **Compile-time weaving (CTW)** | Biên dịch nguồn và weave trong cùng bước | Compiler hiểu aspect, nguồn Java/aspect, compilation level, classpath, output |
| **Post-compile / binary weaving (PCW)** | Sau khi Java đã tạo `.class` hoặc JAR | Weaver task, binary input (`-inpath`), aspect nguồn hoặc thư viện (`-aspectpath`), output riêng |
| **Load-time weaving (LTW)** | Khi JVM classloader định nghĩa lớp | Aspect đã biên dịch, `aspectjweaver` agent, `META-INF/aop.xml`, runtime classpath, lệnh khởi động |
| **Proxy/interception AOP** | Lời gọi đi qua proxy/interceptor lúc chạy | Thư viện tạo proxy, cấu hình lắp ghép interceptor và phân phối đúng tham chiếu proxy; có thể không cần bytecode weaver |

**Không được nhầm proxy AOP với binary weaving.** Một build chỉ chạy `javac` vẫn có thể dùng AOP dựa trên proxy ở runtime. Ngược lại, AspectJ-style `execution`/`call`/`get`/`set` weaving thường cần compiler/weaver hỗ trợ các join point đó. Việc proxy bị bỏ qua bởi self-invocation không suy ra rằng một execution join point đã được weave cũng bị bỏ qua.

Phần hướng dẫn cụ thể sau dùng **AspectJ và công cụ `ajc`** làm ví dụ cho AOP dệt mã Java; các nguyên tắc về thứ tự tác vụ, tính đúng đắn của artifact và kiểm thử áp dụng rộng hơn. Cú pháp và hỗ trợ join point của các công cụ AOP khác có thể khác nhau.

## 3. Xác định rõ hợp đồng đầu vào/đầu ra

Một pipeline dệt mã có thể biểu diễn như sau:

```text
Java source + Aspect source + dependencies
                       |
                       v
              Aspect-aware compiler (CTW)
                       |
                       v
                 Woven .class/JAR
                       |
               test -> package -> run

Java source --javac--> Plain .class/JAR
                              |
Plain .class/JAR + Aspect binary + weaver
                              |
                              v
                       Woven .class/JAR (PCW)
                              |
                       test -> package -> run

Plain .class/JAR + compiled aspects + aop.xml
                              |
                 JVM + weaving javaagent (LTW)
                              |
                       Woven code in memory
```

Khác biệt cốt lõi:

- **CTW:** mã đã dệt được lưu thành artifact sau biên dịch; lúc chạy thường chỉ cần các runtime dependencies tương ứng. Không cần agent chỉ để kích hoạt những advice đã weave.
- **PCW:** giữ `plain classes` và `woven classes` ở **hai thư mục/JAR khác nhau**, nhờ đó tránh ghi đè đầu vào và biết chính xác artifact nào phải được phát hành.
- **LTW:** artifact ứng dụng có thể vẫn là class chưa weave; tính năng AOP phụ thuộc cả **lệnh khởi động JVM**, `aspectjweaver`, aspect và cấu hình được tìm thấy ở runtime. Chỉ thêm dependency lúc biên dịch không tự bật agent.
- **Proxy:** build chịu trách nhiệm có đúng thư viện/runtime configuration, nhưng pointcut có thể được đánh giá tại proxy boundary thay vì biến đổi bytecode.

Trong mọi pipeline, **test phải chạy trên output mà production sẽ sử dụng**. Nếu test chạy trên các class chưa weave còn gói phát hành chứa woven classes (hoặc ngược lại), kết quả test sẽ gây hiểu nhầm.

## 4. Dependency và các tham số thường gặp của `ajc`

Ba artifact có vai trò khác nhau trong một cấu hình AspectJ điển hình:

| Artifact | Vai trò |
| --- | --- |
| `org.aspectj:aspectjtools` | Chứa compiler/weaver `org.aspectj.tools.ajc.Main`, dùng khi build |
| `org.aspectj:aspectjrt` | Runtime các type cần thiết cho aspect đã biên dịch/weave, dùng ở runtime của ứng dụng |
| `org.aspectj:aspectjweaver` | Weaving engine và Java agent; quan trọng với LTW, không tự biến build CTW thành LTW |

Các tùy chọn chính:

| Tùy chọn `ajc` | Ý nghĩa | Nhầm lẫn thường gặp |
| --- | --- | --- |
| `-classpath` | Các type/dependency mà compiler cần để phân giải tên và liên kết | Nó **không đồng nghĩa** danh sách các class phải weave |
| `-inpath` | Thư mục/JAR chứa bytecode đầu vào để **binary weave** | Không lấy đầu vào trực tiếp từ mọi thư viện chỉ vì chúng nằm trên classpath |
| `-aspectpath` | Thư mục/JAR chứa **binary aspects** để dệt vào nguồn/inpath | Không thay thế `-classpath` cho mọi class được tham chiếu |
| `-d` | Thư mục đặt các class kết quả | Không ghi lên cùng nơi lưu inpath khi có thể tránh |
| `-outjar` | Ghi kết quả build thành JAR | Đảm bảo JAR được phát hành chính là kết quả đã weave |
| `-source`, `-target`, `-17` | Chọn phiên bản cú pháp/bytecode tương ứng | Không mặc định tương thích với JDK chạy `ajc` nếu compiler quá cũ |
| `-showWeaveInfo` | In ra thông báo về các lời ghép join point/advice | Thiếu output có thể do matcher không khớp hoặc không có class cần weave |
| `-Xlint:warning` / `-Xlint:error` | Phát hiện vấn đề AOP đáng chú ý | Không phải mọi warning đều chứng minh runtime sai; cần phân loại |
| `-sourceroots` / `@argfile` | Chỉ ra tập nguồn/argument file | `ajc` không tự tìm mọi nguồn cần thiết như mong đợi từ `javac` |

`-inpath` và `-aspectpath` nhận một đối số đường dẫn, dùng dấu phân cách `:` trên Linux/macOS hoặc `;` trên Windows. Khi gọi từ build tool, nên dựng classpath bằng API của tool thay vì tự ghép theo hệ điều hành. Các binary aspect từ `-aspectpath` phải tương thích với compiler đang weave; giữ phiên bản runtime/compiler phù hợp để dễ tái hiện.

Không có một “bản AspectJ mới nhất” cố định cho mọi dự án. Khi nâng Java language level, kiểm tra ma trận hỗ trợ JDK/compiler của phiên bản `ajc` đã chọn và khóa phiên bản trong build. Những phiên bản viết dưới đây là **ví dụ xác định để học và tái hiện**, cần rà soát theo chính sách dependency của dự án khi áp dụng lâu dài.

## 5. Ví dụ tối thiểu chạy được: Java 17 + compile-time weaving

### 5.1. Cấu trúc file

```text
aop-build-demo/
├── src/
│   └── demo/
│       ├── Main.java
│       └── TraceAspect.aj
└── lib/
    ├── aspectjtools-1.9.22.jar
    └── aspectjrt-1.9.22.jar
```

Tải hai JAR đúng tọa độ Maven `org.aspectj:aspectjtools:1.9.22` và `org.aspectj:aspectjrt:1.9.22` từ kho dependency tin cậy. Đây là hai dependency riêng; tên file trong ví dụ giả định JAR đã được đặt trong `lib/`.

**`src/demo/Main.java`**:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        work();
    }

    static void work() {
        System.out.println("business work");
    }
}
```

**`src/demo/TraceAspect.aj`**:

```java
package demo;

public aspect TraceAspect {
    before(): execution(void demo.Main.work()) {
        System.out.println("advice before work");
    }
}
```

Đây là **AspectJ code-style aspect**, file `.aj` cần compiler hiểu AspectJ. Lệnh `javac` thuần túy không biên dịch cú pháp `public aspect` và `before(): ...`. Pointcut chọn execution của `Main.work()`, không chọn `Main.main()`.

### 5.2. Biên dịch và chạy trên Linux/macOS

Chạy trong thư mục `aop-build-demo/` với JDK 17+ và hai JAR đã có:

```bash
mkdir -p out/ctw
java -cp "lib/aspectjtools-1.9.22.jar:lib/aspectjrt-1.9.22.jar"   org.aspectj.tools.ajc.Main   -17 -classpath "lib/aspectjrt-1.9.22.jar"   -showWeaveInfo -d out/ctw   src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out/ctw:lib/aspectjrt-1.9.22.jar" demo.Main
```

Trên Windows PowerShell, lệnh tương ứng (đã có sẵn thư mục `out/ctw`):

```powershell
New-Item -ItemType Directory -Force out/ctw | Out-Null
java -cp "lib/aspectjtools-1.9.22.jar;lib/aspectjrt-1.9.22.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib/aspectjrt-1.9.22.jar" -showWeaveInfo -d out/ctw src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out/ctw;lib/aspectjrt-1.9.22.jar" demo.Main
```

**Standard output của ứng dụng** (không tính thông báo dệt trong bước `ajc`):

```text
advice before work
business work
```

Giải thích: `ajc` nhận **cả nguồn nghiệp vụ lẫn aspect** trong cùng phép biên dịch và tạo class đã weave ở `out/ctw`. Khi chạy `demo.Main`, không cần `-javaagent` bởi advice đã nằm trong bytecode đầu ra. Thông báo `-showWeaveInfo` của bước build giúp chứng minh weaver đã chọn join point mong muốn; dạng văn bản chi tiết có thể thay đổi theo phiên bản.

**Phép đối chứng:** nếu chỉ chạy `javac -d out/plain src/demo/Main.java` rồi chạy `java -cp out/plain demo.Main` thì output chỉ còn `business work`. Đây là hai artifact khác nhau, không phải pointcut tự thay đổi.

### 5.3. Phân biệt compile-time weaving và post-compile weaving

Cũng với hai file nguồn trên, có thể tách biên dịch Java trước, biên dịch aspect riêng, rồi weave binary:

```bash
mkdir -p out/plain out/aspects out/woven
javac -d out/plain src/demo/Main.java

java -cp "lib/aspectjtools-1.9.22.jar:lib/aspectjrt-1.9.22.jar"   org.aspectj.tools.ajc.Main -17   -classpath "out/plain:lib/aspectjrt-1.9.22.jar"   -d out/aspects src/demo/TraceAspect.aj

java -cp "lib/aspectjtools-1.9.22.jar:lib/aspectjrt-1.9.22.jar"   org.aspectj.tools.ajc.Main -17   -classpath "out/plain:out/aspects:lib/aspectjrt-1.9.22.jar"   -inpath out/plain -aspectpath out/aspects   -d out/woven -showWeaveInfo

java -cp "out/woven:out/aspects:lib/aspectjrt-1.9.22.jar" demo.Main
```

**Output ứng dụng mong đợi vẫn là:**

```text
advice before work
business work
```

Ở ví dụ PCW, `out/plain` là input cho `-inpath`; `out/aspects` là binary aspects dùng qua `-aspectpath`; `out/woven` là class sau khi biến đổi. Không sử dụng `out/plain` trong lệnh chạy cuối. Trên Windows, thay dấu `:` phân tách path bằng `;` trong những tham số classpath, giữ các tùy chọn khác như cũ.

Đầu vào `-inpath` có thể là JAR đã biên dịch, không chỉ thư mục. Trong build thực tế, **không nên đưa cùng một class từ nhiều input vào weaver**, hay dùng thư mục `-d` lại làm `-inpath` ở lượt build sau: có thể gây weaving lặp, xung đột hoặc đầu ra khó tái hiện.

## 6. Khai báo Maven trong lifecycle build

Maven đặt trọng tâm vào việc gắn các goal biên dịch/weaving vào các phase được chạy bởi `mvn clean test` và `mvn package`. Ví dụ sau là **một POM cơ bản đầy đủ** cho dự án Java 17 chứa mã nguồn Java và file `.aj`; các phiên bản dependency được cố định minh họa để có thể tái hiện.

Tổ chức lại code ở phần 5:

```text
aop-maven-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/Main.java
        └── aspect/demo/TraceAspect.aj
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>aop-maven-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjrt</artifactId>
      <version>1.9.22</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>dev.aspectj</groupId>
        <artifactId>aspectj-maven-plugin</artifactId>
        <version>1.14.1</version>
        <configuration>
          <complianceLevel>17</complianceLevel>
          <aspectDirectory>src/main/aspect</aspectDirectory>
          <showWeaveInfo>true</showWeaveInfo>
        </configuration>
        <executions>
          <execution>
            <goals>
              <goal>compile</goal>
              <goal>test-compile</goal>
            </goals>
          </execution>
        </executions>
        <dependencies>
          <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjtools</artifactId>
            <version>1.9.22</version>
          </dependency>
        </dependencies>
      </plugin>
    </plugins>
  </build>
</project>
```

Chạy:

```bash
mvn clean package
```

Lưu ý triển khai:

- Plugin `dev.aspectj:aspectj-maven-plugin` chạy `ajc` theo mục tiêu `compile` và `test-compile`. `aspectjtools` là **plugin dependency** để plugin dùng đúng compiler; `aspectjrt` là **project dependency** vì mã đã dệt có thể cần type runtime của AspectJ.
- Dùng `complianceLevel` **hoặc** cấu hình `source`/`target` phù hợp; không chồng nhiều chỉ tiêu bất nhất. Với mã Java 17, phiên bản compiler chạy build cũng cần hỗ trợ Java 17.
- Nguồn Java và aspect phải đặt đúng directory plugin được cấu hình. Nếu có module chứa binary aspect riêng, phụ thuộc aspect và cấu hình weaving tại module tiêu thụ phải được khai báo tường minh; chỉ thêm `aspectjrt` không đồng nghĩa áp dụng những aspect đó.
- Nếu có cả bộ biên dịch Java mặc định và `ajc` trong cùng lifecycle, cần hiểu thứ tự và bảo đảm **artifact cuối** chứa class đã weave. Kiểm tra `target/classes` và JAR sau `mvn clean package`; đừng chỉ thấy “BUILD SUCCESS” rồi suy ra advice đã chạy.
- `test-compile` dành cho nguồn test và weaving test nếu cần. Một phép thử integration cần thực thi chính class sau weave; nếu các test nạp output ở nơi khác, có thể cho kết quả giả.

Điều chỉnh phiên bản plugin/compiler dựa trên tài liệu và compatibility matrix đang áp dụng cho hệ thống; không nên vô điều kiện sao chép một cấu hình được viết cho Java level khác.

## 7. Khai báo Gradle: mô hình tác vụ và output

Gradle thường cần một **task rõ ràng** để chạy compiler/weaver, sau đó nối nó vào graph `compile → weave → test/package`. Một mô hình phối hợp tốt:

```text
compileJava ------------------+
                              v
                          weaveMain
                              |
                     +--------+---------+
                     v                  v
               testWovenClasses      wovenJar
                                        |
                                        v
                                    publish
```

Đặc điểm quan trọng: Gradle có thể coi `compileJava` là producer của `build/classes/java/main`, trong khi `weaveMain` phải có **thư mục output riêng** `build/woven/main`. Đừng viết đè ngược trở lại output của `compileJava` nếu task tracking/cache đang giả định output đó không thay đổi.

Ví dụ **khung cấu hình Gradle Groovy DSL** cho *binary weaving của class đã biên dịch* (giả sử thư viện chứa aspect binary được cấu hình riêng):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

configurations {
    ajcTools
    binaryAspects
}

dependencies {
    implementation 'org.aspectj:aspectjrt:1.9.22'
    ajcTools 'org.aspectj:aspectjtools:1.9.22'
    binaryAspects files('libs/aspects.jar')
}

def wovenDirectory = layout.buildDirectory.dir('woven/main')

tasks.register('weaveMain', JavaExec) {
    dependsOn tasks.named('compileJava')
    classpath = configurations.ajcTools
    mainClass = 'org.aspectj.tools.ajc.Main'

    doFirst {
        def output = wovenDirectory.get().asFile
        output.mkdirs()
        def plainClasses = tasks.named('compileJava').get()
            .destinationDirectory.get().asFile
        args '-17',
             '-classpath', sourceSets.main.compileClasspath.asPath,
             '-inpath', plainClasses.absolutePath,
             '-aspectpath', configurations.binaryAspects.asPath,
             '-d', output.absolutePath,
             '-showWeaveInfo'
    }
}

tasks.register('wovenJar', Jar) {
    dependsOn tasks.named('weaveMain')
    archiveClassifier = 'woven'
    from(wovenDirectory)
    from(sourceSets.main.output.resourcesDir)
}
```

Đây là **khung dành cho dự án đã có** file `libs/aspects.jar` được biên dịch riêng bằng AspectJ; nó không tự tạo file đó. Phải thêm aspect JAR vào dependency classpath phù hợp nếu ứng dụng cần tham chiếu các type trong JAR. Một pipeline multi-project nên thay đường dẫn file bằng dependency project/artifact có version kiểm soát được.

Sau khi gắn các task, chạy:

```bash
gradle clean wovenJar
```

Kiểm tra JAR có classifier `woven` chứa **class từ `build/woven/main`**, không vô tình phát hành JAR mặc định chứa class chưa dệt. Trong dự án thực, thêm task test chạy trên woven classes và dependency classpath cần thiết. Với task muốn được cache chuẩn, khai báo `inputs`/`outputs` tương ứng, tránh tạo tham số ngoài task action làm Gradle không nhìn thấy dependency, và không dùng cùng directory cho cả input lẫn output. Mẫu khung trên cố tình tách `wovenJar` để phân biệt rõ artifact đã weave với artifact Java mặc định.

Nếu dùng plugin Gradle ngoài thay vì gọi `ajc` trực tiếp, hãy kiểm tra plugin được duy trì, hỗ trợ phiên bản Gradle/JDK đang dùng và thực sự nối task weaving vào `test`, `jar`, `publish`. **Thấy dependency AspectJ trong `build.gradle` không bảo đảm weaving được chạy.**

## 8. Load-time weaving: khai báo ở build và ở JVM

LTW không dệt class trong quá trình build thông thường. Build cần cung cấp ba thứ: **application classes**, **aspect classes đã biên dịch**, và **`META-INF/aop.xml`** ở runtime classpath; môi trường khởi động JVM cần thêm weaving agent.

Ví dụ cấu hình **`src/main/resources/META-INF/aop.xml`** cho một aspect đã được biên dịch với tên đầy đủ `demo.TraceAspect`:

```xml
<!DOCTYPE aspectj PUBLIC
  "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <aspects>
    <aspect name="demo.TraceAspect"/>
  </aspects>
  <weaver options="-verbose -showWeaveInfo">
    <include within="demo..*"/>
  </weaver>
</aspectj>
```

*Đây là đoạn cấu hình*, không phải chương trình chạy độc lập. Cần bảo đảm file được đóng gói dưới đường dẫn chính xác `META-INF/aop.xml` và aspect class `demo.TraceAspect` được nạp qua classloader mà weaver nhìn thấy.

**Lệnh JVM minh họa** trên Linux/macOS sau khi đã chuẩn bị `app.jar`, `aspects.jar`, runtime và agent đúng phiên bản:

```bash
java -javaagent:lib/aspectjweaver-1.9.22.jar   -cp "app.jar:aspects.jar:lib/aspectjrt-1.9.22.jar"   demo.Main
```

Môi trường Windows dùng dấu `;` cho `-cp`. Tên JAR trong ví dụ biểu diễn artifact đã được build/đặt vào đúng nơi; chỉ gắn agent không tự tạo `app.jar`, `aspects.jar` hoặc `aop.xml`. Nếu file cấu hình nằm trong `aspects.jar` hoặc `app.jar` và được đóng gói đúng cấu trúc, weaver mới có thể đọc nó.

Các ràng buộc LTW đặc biệt quan trọng:

- **Agent phải được gắn trước khi các lớp cần dệt được định nghĩa.** Khai báo aspect sau khi classloader đã load lớp có thể khiến join point bị bỏ lỡ.
- **Classloader xác định phạm vi nhìn thấy.** Weaver không tự dệt các lớp đã do classloader cha định nghĩa.
- **Tách cấu hình build với runtime.** Maven/Gradle tải `aspectjweaver` vào dependency tree không có nghĩa lệnh `java` cuối cùng có `-javaagent`.
- **Giữ CTW/PCW và LTW có chủ đích.** Nếu đưa artifact đã weave vào môi trường LTW, phải hiểu reweaving và bảo đảm cấu hình không dệt trùng ngoài thiết kế.
- **Đóng gói và triển khai đồng bộ.** Docker entrypoint, lệnh start service, test launcher và staging/prod phải nhận cùng agent, aspect JAR, classpath và cấu hình.

Khi điều tra LTW, bật `-verbose` và `-showWeaveInfo` trên môi trường tái hiện có kiểm soát, ghi danh sách classloader và kiểm tra file `aop.xml` thực sự có trên classpath.

## 9. Thiết kế pipeline build có thể tái hiện

Một pipeline đáng tin cậy có các bước theo quan hệ phụ thuộc:

1. **Resolve phiên bản:** khóa JDK toolchain, `aspectjtools`, `aspectjrt`, `aspectjweaver` (nếu có), plugin và các aspect library. Đảm bảo version nâng cấp được kiểm soát.
2. **Compile aspect và Java:** CTW cho nguồn do mình sở hữu, hoặc `javac` rồi chuẩn bị binary aspects để PCW.
3. **Weave:** thực thi task từ dữ liệu đầu vào được xác định; tạo woven output vào một nơi riêng, ghi rõ diagnostics.
4. **Test trên woven output:** chạy unit/integration test với classpath chứa artifact đúng và runtime dependencies. Nếu dùng LTW, test phải truyền agent và file cấu hình tương đương production.
5. **Package:** ưu tiên đóng gói duy nhất artifact đã xác nhận có weaving, hoặc đóng gói plain artifact cùng yêu cầu LTW được khai báo rõ.
6. **Publish/deploy:** xuất bản hash, version, artifact coordinates và hướng dẫn JVM flags; phát hành cùng chính file được test.
7. **Smoke test sau triển khai:** kiểm tra một join point có giá trị đại diện tạo advice đúng một lần, và một negative case không bị bắt nhầm.

Những lựa chọn kiến trúc cần cân nhắc:

- **Source code sẵn có:** CTW thường rõ ràng nhất nếu aspect cần inter-type declarations hoặc mã Java dựa trực tiếp vào các thành viên aspect thêm vào.
- **Thư viện bên ngoài chỉ có binary:** PCW thích hợp khi được phép biến đổi class/JAR; chú ý giấy phép, chữ ký JAR và provenance của artifact mới.
- **Muốn thay phạm vi weave theo môi trường:** LTW cung cấp cấu hình lúc load nhưng tăng yêu cầu về JVM flags/classloader và debugging.
- **Chỉ cần chặn API boundary:** proxy/interception có thể đủ, không cần `ajc`; phải chấp nhận giới hạn lời gọi không qua proxy.

Với dự án nhiều module, module chứa aspect phải được build trước module dùng nó; tuy nhiên chỉ việc “module aspect đã build” chưa khiến module nghiệp vụ được weave. Nối dependency **và** weaving task/goal ở nơi tiêu thụ, rồi kiểm tra bytecode của module đó.

## 10. Chứng minh build thực sự đã dệt aspect

Không dùng một mình exit code 0 hoặc dòng “BUILD SUCCESS” làm bằng chứng. Cần kết hợp:

| Bằng chứng | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| Log `-showWeaveInfo` | Compiler/weaver cho thấy join point nào nhận advice | Log có thể tắt, và lời match chưa chứng minh artifact đúng đã được chạy |
| `jar tf app.jar` | Xác định class/resource có nằm trong JAR phát hành | Không xác định chính xác advice đã được weave chỉ từ tên class |
| `javap -c -p` hoặc so hash bytecode | Kiểm tra class đầu ra khác lớp nguyên bản như kỳ vọng | Compiler tối ưu hoặc metadata khác cũng làm bytecode khác; cần đọc kỹ |
| Smoke test positive | Đường chạy đại diện thực sự thực thi advice | Chưa bao phủ mọi signature/runtime condition |
| Smoke test negative | Đảm bảo pointcut không rộng gây side effect ngoài phạm vi | Không thay thế kiểm thử đặc tính join point phức tạp |
| Classpath/JVM startup log | Chứng minh LTW agent/cấu hình đã khởi động | Agent bật nhưng class đã load sớm hoặc bị loại vẫn không weave |

Phép thử khói tối thiểu đối với ví dụ `demo.Main`: khi chạy woven output, chương trình in đúng hai dòng `advice before work` rồi `business work`. Khi chạy plain output, chỉ in một dòng nghiệp vụ. Hai phép thử giúp chỉ ra build đã tác động thật, thay vì lời advice ngẫu nhiên có mặt do một môi trường runtime khác.

Đối với hệ thống đang chạy, nên kiểm tra một phương thức có pointcut hẹp, không gây side effect; không chọn giao dịch thanh toán/ghi dữ liệu làm smoke test nếu chưa có môi trường cô lập.

## 11. Lỗi build và cách xử lý theo nguyên nhân

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra/sửa |
| --- | --- | --- |
| `javac` báo lỗi với `aspect`, `before()` | Đã đưa cú pháp `.aj` cho Java compiler thường | Dùng `ajc` cho mã AspectJ, cấu hình đúng source roots |
| `ajc` không tìm được type | Thiếu `-classpath` hoặc nguồn phụ thuộc, module build sai thứ tự | Liệt kê dependency thực và source list |
| `ajc` chạy thành công nhưng không weave | Target classes ngoài nguồn/inpath, sai pointcut, thiếu aspectpath | Kiểm tra `-showWeaveInfo` và class được xử lý |
| Chạy ứng dụng không thấy advice | Đã build woven output nhưng classpath chạy plain output | So command line, JAR được phát hành và actual loaded classes |
| Class bị weave hai lần | Pipeline có CTW rồi PCW, hoặc output cũ quay lại `-inpath` | Tách đầu vào/đầu ra, kiểm tra graph và clean build |
| Lỗi `NoClassDefFoundError` liên quan AspectJ | Runtime classpath thiếu `aspectjrt` hoặc aspect library | Gắn đúng runtime dependencies vào package/launcher |
| LTW im lặng | Không truyền `-javaagent`, thiếu `aop.xml`, agent không thấy aspect | Xem lệnh JVM thực, JAR content, verbose weaver log |
| LTW bỏ sót class | Classload trước agent/cấu hình, classloader khác, exclude pattern | Kiểm tra thời điểm load, classloader và phạm vi include/exclude |
| Test qua nhưng production sai | Test/production dùng artifact khác hoặc thiếu agent ở một môi trường | Đồng nhất test launcher, artifact hash và startup flags |
| Incremental build lúc đúng lúc sai | Không khai báo inputs/outputs cho weave task, cache cũ hoặc output đè input | Khai báo graph chuẩn, rebuild sạch để đối chiếu, sửa cache dependencies |

**Các lỗi cần tránh:** chỉ thêm một dependency rồi cho rằng đã weave; dùng `-classpath` thay `-inpath`; đưa class đầu ra đã weave vào lại bước weaving không kiểm soát; đóng gói plain classes sau khi weave thành công; bỏ qua logs warning về những join point không match; hoặc quên truyền agent khi triển khai LTW.

## 12. Checklist cho code review và CI

- [ ] Đã chọn rõ **CTW, PCW, LTW hoặc proxy interception** theo yêu cầu join point.
- [ ] Compiler và runtime đã được khóa phiên bản, hỗ trợ đúng JDK và bytecode target.
- [ ] Nguồn Java, source aspect, binary aspect và các thư viện đã gắn vào đúng classpath/source roots.
- [ ] `-inpath`, `-aspectpath`, `-d` và `-outjar` (nếu có) được sử dụng đúng nghĩa.
- [ ] Build graph có quan hệ `compile → weave → test → package` đúng hướng; không bỏ qua step weaving khi CI chạy.
- [ ] Đầu vào và đầu ra weaving không ghi đè lẫn nhau; cache/clean build dễ tái hiện.
- [ ] Class/JAR được test chính là class/JAR được phát hành; không vô tình dùng plain output.
- [ ] Có positive/negative tests chứng minh pointcut tác động đúng nơi và đúng số lần.
- [ ] Với LTW: `META-INF/aop.xml`, aspect, runtime dependency và `-javaagent` đều hiện diện khi chạy.
- [ ] Đã xem weave diagnostics và các cảnh báo quan trọng; không mặc định “BUILD SUCCESS” là “AOP SUCCESS”.
- [ ] Đã kiểm tra classloader, module boundary, executable JAR/container packaging khi hệ thống có chúng.

## 13. Tài liệu chính thống để đối chiếu theo phiên bản

- [Tài liệu `ajc` của Eclipse AspectJ](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): tham số compiler, `-inpath`, `-aspectpath`, compiler level và diagnostics.
- [Load-Time Weaving của Eclipse AspectJ](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): cấu hình `META-INF/aop.xml`, agent, classloader và phạm vi weave.
- [AspectJ Maven Plugin](https://github.com/dev-aspectj/aspectj-maven-plugin): cách chạy compiler AspectJ từ Maven, gắn compiler/runtime versions.
- [AspectJ Maven Plugin Usage](https://dev-aspectj.github.io/aspectj-maven-plugin/usage.html): goal `compile` và `test-compile`.

**Nguyên tắc thực hành:** build phải xác định **điểm weave, tập bytecode đầu vào, aspect được áp dụng và artifact chạy cuối cùng**. Khi bốn yếu tố đó rõ ràng, việc bổ sung AOP trở thành một bước có thể kiểm thử và tái hiện, thay vì phụ thuộc vào một thiết lập IDE hoặc một JVM flag dễ bị bỏ sót.
