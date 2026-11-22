# Ant, Make, Maven và Gradle: khác biệt về mô hình và phạm vi sử dụng

## 1. Build tool làm nhiệm vụ gì?

Build tool tự động hóa các bước biến mã nguồn và tài nguyên của dự án thành sản phẩm có thể kiểm thử, phân phối hoặc triển khai. Tùy dự án, quy trình này có thể gồm:

- Biên dịch mã nguồn.
- Tải và quản lý thư viện phụ thuộc.
- Chạy kiểm thử và các bước kiểm tra chất lượng.
- Đóng gói thành executable, thư viện, JAR, WAR hoặc sản phẩm khác.
- Tạo tài liệu, sinh mã, sao chép tài nguyên và chuẩn bị bản phát hành.

Build tool không nhất thiết là compiler. Chẳng hạn, Make có thể gọi GCC hoặc Clang; Ant, Maven và Gradle có thể gọi Java compiler. Build tool mô tả **công việc nào cần chạy, phụ thuộc vào công việc nào và khi nào cần chạy lại**. Compiler chỉ thực hiện một phần công việc trong quy trình đó.

Make, Ant, Maven và Gradle đều có thể tự động hóa build, nhưng chúng xuất phát từ những mô hình khác nhau. Vì vậy, chúng phù hợp với những kiểu dự án và mức độ chuẩn hóa khác nhau.

## 2. Make: mô hình mục tiêu và phụ thuộc giữa các tệp

Make xuất phát từ nhu cầu xây dựng chương trình bằng cách theo dõi quan hệ phụ thuộc giữa các tệp. Một quy tắc thường có ba phần:

- **Target**: tệp hoặc mục tiêu cần tạo.
- **Prerequisites**: các tệp mà target phụ thuộc vào.
- **Recipe**: lệnh shell dùng để tạo hoặc cập nhật target.

Make so sánh thời điểm sửa đổi của target và các prerequisite. Nếu target chưa tồn tại hoặc một prerequisite mới hơn target, recipe tương ứng sẽ được chạy. Nhờ vậy, một lần build sau thường chỉ phải xử lý những phần có thay đổi.

Ví dụ Makefile cho một chương trình C nhỏ:

```make
CC ?= cc
CFLAGS ?= -Wall -Wextra -O2

hello: main.o util.o
	$(CC) $(CFLAGS) -o $@ $^

main.o: main.c util.h
	$(CC) $(CFLAGS) -c -o $@ main.c

util.o: util.c util.h
	$(CC) $(CFLAGS) -c -o $@ util.c

.PHONY: clean
clean:
	rm -f hello main.o util.o
```

Khi chạy `make`, Make đọc quan hệ phụ thuộc, xác định những target cần cập nhật rồi chạy recipe. Nếu chỉ sửa `util.c`, Make có thể biên dịch lại `util.o` và liên kết lại chương trình mà không cần biên dịch lại `main.o`.

**Điểm mạnh**

- Mô hình đơn giản, trực tiếp và hiệu quả với quan hệ phụ thuộc ở mức tệp.
- Phù hợp với C/C++, thư viện native, công cụ hệ thống và các dự án cần gọi lệnh tùy biến.
- Có mặt rộng rãi trên môi trường Unix-like và thường được dùng trong các chuỗi công cụ native.

**Giới hạn**

- Make không cung cấp sẵn một hệ thống quản lý dependency Maven Central hay một lifecycle Java chuẩn.
- Người viết Makefile phải mô tả quan hệ phụ thuộc đủ chính xác. Nếu bỏ sót header, generated file hoặc một đầu vào khác, build tăng dần có thể cho kết quả sai.
- Recipe thường là lệnh shell, nên khác biệt giữa môi trường có thể ảnh hưởng đến tính di động.
- Khi dự án lớn, nhiều cấu hình và nhiều nền tảng, Makefile có thể trở nên khó tổ chức và bảo trì.

Make tập trung vào câu hỏi: **tệp đầu ra này phụ thuộc vào những đầu vào nào, và cần chạy lệnh gì để tạo nó?**

## 3. Apache Ant: mô hình target và task

Ant được xây dựng trên nền Java và mô tả quy trình build trong tệp XML, thường là `build.xml`. Một project có nhiều **target**; mỗi target chứa một chuỗi **task** và có thể khai báo target khác phải chạy trước bằng thuộc tính `depends`.

Ant cung cấp các task cho những việc phổ biến như biên dịch Java, tạo JAR, sao chép tệp, xóa thư mục và chạy chương trình. Người viết build file chủ động chỉ định các bước và thứ tự thực hiện.

Ví dụ:

```xml
<project name="hello" default="jar" basedir=".">
    <property name="src.dir" value="src"/>
    <property name="build.dir" value="build"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac
            srcdir="${src.dir}"
            destdir="${build.dir}/classes"
            includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${build.dir}/dist"/>
        <jar
            destfile="${build.dir}/dist/hello.jar"
            basedir="${build.dir}/classes"/>
    </target>
</project>
```

Lệnh `ant jar` chạy target `compile` trước, sau đó chạy các task trong target `jar`. Các task trong cùng target được thực hiện theo thứ tự khai báo.

Ant có thể biểu diễn quan hệ phụ thuộc giữa các target, nhưng trọng tâm của nó là **điều phối target và task do người viết khai báo**. Nó không tự áp đặt một lifecycle Java và cấu trúc thư mục chuẩn như Maven. Ant core cũng không có hệ thống quản lý dependency thư viện tích hợp tương đương Maven; dự án có thể bổ sung Apache Ivy hoặc cơ chế khác.

**Điểm mạnh**

- Linh hoạt khi cần quy trình build riêng, nhiều bước xử lý tệp hoặc tích hợp công cụ bên ngoài.
- Phù hợp với các dự án Java cũ đã có build file Ant và các quy trình khó chuyển ngay sang mô hình chuẩn.
- Các task XML có thể đọc được và dễ ghép thành quy trình rõ ràng.

**Giới hạn**

- XML có thể dài và lặp lại nhiều cấu hình khi dự án lớn.
- Người viết phải tự thiết kế phần lớn quy ước, cấu trúc thư mục và quy trình.
- Quản lý thư viện, phiên bản và dependency bắc cầu cần công cụ hoặc cấu hình bổ sung.
- Nhiều dự án tự xây dựng cách tổ chức khác nhau, khiến việc chuyển đổi và dùng chung quy ước khó hơn.

Ant tập trung vào câu hỏi: **quy trình build gồm những target và task nào, và chúng cần chạy theo thứ tự nào?**

## 4. Maven: mô hình project khai báo và lifecycle chuẩn

Maven hướng đến việc chuẩn hóa cách mô tả và build dự án, đặc biệt trong hệ sinh thái Java. Thông tin dự án được khai báo trong `pom.xml` (Project Object Model), gồm tọa độ artifact, phiên bản, dependency, plugin và cấu hình build.

Maven cung cấp cấu trúc thư mục mặc định, chẳng hạn:

```text
src/
├── main/
│   ├── java/
│   └── resources/
└── test/
    ├── java/
    └── resources/
```

Dự án có thể dùng cấu trúc mặc định mà không cần khai báo lại mọi đường dẫn. Maven cũng có các lifecycle với những phase tiêu chuẩn. Một phần lifecycle mặc định thường gặp là:

```text
validate → compile → test → package → verify → install → deploy
```

Khi chạy `mvn package`, Maven thực hiện các phase đứng trước trong lifecycle tương ứng rồi đóng gói sản phẩm. Các plugin gắn goal vào những phase để thực hiện việc cụ thể, ví dụ biên dịch, chạy test hoặc tạo JAR.

Ví dụ POM tối giản:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Dependency được khai báo bằng tọa độ như `groupId`, `artifactId` và `version`. Maven tải artifact từ repository, lưu vào local repository và tự giải quyết các dependency bắc cầu theo quy tắc của nó. Nhờ vậy, người viết không phải tự tải từng JAR rồi thêm thủ công vào classpath.

**Điểm mạnh**

- Quy ước rõ ràng giúp dự án Java có cấu trúc quen thuộc giữa các nhóm.
- Lifecycle tiêu chuẩn giúp người khác dễ hiểu các lệnh build và kết quả mong đợi.
- Quản lý dependency, phiên bản, repository và dependency bắc cầu được tích hợp.
- Hệ sinh thái plugin lớn, phù hợp với thư viện, ứng dụng và dịch vụ Java có quy trình tương đối chuẩn.

**Giới hạn**

- Cấu trúc và lifecycle chuẩn có thể gây khó chịu khi dự án có quy trình đặc biệt hoặc cần điều phối nhiều bước không theo mô hình Maven.
- Việc tùy chỉnh sâu thường phải hiểu cách plugin và goal được gắn vào lifecycle.
- POM XML có thể dài khi có nhiều profile, plugin hoặc cấu hình kế thừa.

Maven tập trung vào câu hỏi: **dự án này là artifact nào, cần dependency nào và phải đi qua lifecycle chuẩn nào để tạo ra artifact đó?**

## 5. Gradle: mô hình task graph và build logic có thể mở rộng

Gradle kết hợp khả năng điều phối task với hệ thống plugin và quản lý dependency. Build logic thường được viết trong `build.gradle` bằng Groovy DSL hoặc `build.gradle.kts` bằng Kotlin DSL.

Plugin bổ sung task, cấu hình và quy ước cho loại dự án tương ứng. Ví dụ Java plugin tạo các source set và những task quen thuộc như `compileJava`, `test`, `jar` và `build`. Người viết có thể khai báo dependency, cấu hình task có sẵn hoặc tạo task riêng.

Ví dụ `build.gradle` dùng Groovy DSL:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}

tasks.test {
    useJUnitPlatform()
}
```

Khi chạy `gradle build`, Gradle xác định task graph cần thực hiện dựa trên task được yêu cầu và các quan hệ phụ thuộc giữa chúng. Với Java plugin, task `build` tổng hợp các công việc cần thiết để kiểm tra và tạo sản phẩm.

Gradle phân biệt hai phần quan trọng:

1. **Configuration**: đọc build script, áp dụng plugin và cấu hình các task để xác định graph cần chạy.
2. **Execution**: thực thi những task trong graph đã xác định.

Gradle có thể bỏ qua task đã up-to-date khi đầu vào và đầu ra không thay đổi; build cache còn cho phép tái sử dụng kết quả phù hợp giữa các lần build hoặc môi trường được cấu hình để chia sẻ cache. Khả năng này hữu ích với dự án nhiều module và build lớn.

**Điểm mạnh**

- Linh hoạt: có thể dùng quy ước có sẵn của plugin rồi mở rộng khi dự án cần.
- Hỗ trợ dependency management và dependency bắc cầu.
- Có các cơ chế incremental build, build cache và task graph để tối ưu build.
- Phù hợp với dự án JVM nhiều module, Android và các quy trình build cần tùy biến cao.
- Groovy DSL và Kotlin DSL cho phép mô tả build logic có cấu trúc và tái sử dụng.

**Giới hạn**

- Độ linh hoạt lớn đồng nghĩa với việc người viết cần hiểu plugin, task graph và các giai đoạn của Gradle.
- Build script có thể trở thành chương trình phức tạp nếu chứa quá nhiều logic nghiệp vụ hoặc cấu hình tự viết.
- Cần chú ý cách viết task và khai báo đầu vào/đầu ra để incremental build và build cache hoạt động chính xác.
- Plugin và phiên bản Gradle cần được quản lý nhất quán để tránh khác biệt giữa máy lập trình và CI.

Gradle tập trung vào câu hỏi: **task nào cần chạy, task phụ thuộc vào task nào, và làm thế nào cấu hình hoặc mở rộng graph đó cho dự án?**

## 6. So sánh trực tiếp

| Tiêu chí | Make | Ant | Maven | Gradle |
|---|---|---|---|---|
| Mô hình chính | Target và dependency giữa các tệp | Target chứa các task | Project model và lifecycle | Task graph và plugin |
| Tệp cấu hình thường gặp | `Makefile` | `build.xml` | `pom.xml` | `build.gradle` hoặc `build.gradle.kts` |
| Cách mô tả build | Quy tắc và recipe chạy bằng shell | Task XML được sắp xếp trong target | Khai báo project, dependency và plugin | DSL cấu hình plugin, dependency và task |
| Cách quyết định công việc | So sánh target với prerequisite, thường dựa trên thời gian sửa đổi | Chạy target và task theo quan hệ phụ thuộc, thứ tự khai báo | Chạy các phase trong lifecycle và goal của plugin | Tạo task graph rồi thực thi các task cần thiết |
| Quản lý dependency thư viện | Không tích hợp sẵn | Cần công cụ hoặc cơ chế bổ sung, ví dụ Ivy | Tích hợp sẵn, hỗ trợ dependency bắc cầu | Tích hợp sẵn, hỗ trợ dependency bắc cầu |
| Quy ước mặc định | Ít | Ít | Nhiều, đặc biệt cho Java | Do plugin cung cấp và có thể mở rộng |
| Thế mạnh tiêu biểu | Build native, quan hệ phụ thuộc tệp | Quy trình tùy biến, dự án Java cũ | Dự án Java theo quy ước chuẩn | Dự án nhiều module và build logic phức tạp |

Có thể nhìn sự khác biệt qua bốn đơn vị tổ chức:

- Make tổ chức công việc quanh **tệp đầu ra**.
- Ant tổ chức công việc quanh **target và chuỗi task**.
- Maven tổ chức công việc quanh **project model và lifecycle**.
- Gradle tổ chức công việc quanh **task graph do plugin và build logic tạo ra**.

Đây là khác biệt về trọng tâm, không phải ranh giới tuyệt đối. Chẳng hạn, Ant cũng có quan hệ phụ thuộc giữa target; Gradle cũng có quy ước thư mục và lifecycle do plugin cung cấp.

## 7. Chọn công cụ theo phạm vi sử dụng

**Chọn Make khi** dự án chủ yếu cần điều phối compiler và các công cụ native, quan hệ phụ thuộc ở mức tệp là trọng tâm, hoặc hệ sinh thái hiện tại đã dùng Make. Với dự án C/C++ lớn, Make cũng có thể là một phần trong chuỗi công cụ được sinh cấu hình từ một hệ thống build cấp cao hơn.

**Chọn Ant khi** dự án đã có build file Ant ổn định, cần duy trì hệ thống Java cũ hoặc có nhiều bước xử lý đặc thù được mô tả thuận tiện bằng task. Nếu dự án mới cần quản lý dependency và quy ước Java tiêu chuẩn, nên đánh giá Maven hoặc Gradle trước khi chọn Ant.

**Chọn Maven khi** dự án Java có cấu trúc tương đối chuẩn, nhóm muốn một lifecycle thống nhất, dependency được quản lý tập trung và thành viên mới có thể làm quen bằng các lệnh quen thuộc như `mvn test`, `mvn package` hoặc `mvn install`.

**Chọn Gradle khi** dự án cần kết hợp quy ước với khả năng tùy biến, có nhiều module, dùng Android hoặc cần tối ưu thời gian build bằng incremental execution và build cache. Gradle cũng phù hợp khi build logic là một phần đáng kể của hệ thống tự động hóa.

Khi một dự án đã hoạt động ổn định, hệ sinh thái plugin, quy trình CI và kiến thức của nhóm cũng là yếu tố quan trọng. Chuyển công cụ chỉ vì một công cụ mới có nhiều tính năng hơn có thể tạo ra chi phí bảo trì lớn hơn lợi ích nhận được.

## 8. Những điểm cần giữ ổn định trong mọi build

Dù dùng công cụ nào, một build đáng tin cậy cần kiểm soát được các đầu vào ảnh hưởng đến kết quả:

- **Phiên bản công cụ**: thống nhất phiên bản JDK, compiler, build tool và plugin. Với Maven hoặc Gradle, wrapper giúp nhóm và CI dùng cùng phiên bản build tool.
- **Dependency**: khai báo phiên bản có chủ đích, tránh phụ thuộc vào JAR được cài thủ công trên một máy.
- **Đầu vào và đầu ra**: mô tả đầy đủ các tệp hoặc cấu hình mà một bước build sử dụng. Điều này đặc biệt quan trọng với Make và các task incremental của Gradle.
- **Môi trường chạy**: hạn chế giả định về thư mục hiện tại, biến môi trường, shell hoặc công cụ chỉ có trên máy cá nhân.
- **Kiểm thử trên CI**: chạy cùng quy trình build trong môi trường tự động để phát hiện sớm khác biệt giữa máy phát triển và môi trường tích hợp.

Một build script tốt giúp người khác hiểu cách tạo sản phẩm, chạy lại được quy trình và xác định được nguyên nhân khi kết quả thay đổi. Việc chọn Make, Ant, Maven hay Gradle nên bắt đầu từ mô hình build và phạm vi dự án, sau đó mới cân nhắc cú pháp hoặc mức độ quen thuộc của từng công cụ.

