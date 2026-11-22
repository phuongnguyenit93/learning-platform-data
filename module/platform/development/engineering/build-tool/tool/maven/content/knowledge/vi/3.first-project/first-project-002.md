# Sinh dự án từ Maven Archetype và hiểu vai trò của bộ khung

## 1. Vì sao cần một bộ khung khi bắt đầu dự án Java?

Một dự án Java nhỏ vẫn cần nhiều hơn một tệp `App.java`: cần cấu trúc thư mục mà công cụ build hiểu, cấu hình Maven, mã nguồn, kiểm thử và cách đóng gói. Nếu tự tạo từng thứ, người mới dễ quên `pom.xml`, đặt test nhầm chỗ, dùng phiên bản Java không thống nhất hoặc tạo những dự án có cấu trúc khác nhau.

**Maven Archetype** giúp khởi tạo những tệp ban đầu từ **mẫu dự án** đã chuẩn bị sẵn. Đây là một cách tiết kiệm các thao tác lặp lại, đồng thời là cơ hội để học những thành phần Maven kỳ vọng trong một project.

Mục tiêu của bài:

1. Phân biệt **archetype** (mẫu để sinh dự án) và **build lifecycle** (quy trình biên dịch, test, đóng gói).
2. Chạy lệnh sinh dự án Java bằng `maven-archetype-quickstart`.
3. Hiểu vai trò của `pom.xml`, `src/main/java`, `src/test/java`, `.mvn/` và `target/`.
4. Chỉnh mã Java 17 và JUnit 5 trong bộ khung, chạy Maven, kiểm tra kết quả.
5. Nhận ra giới hạn của archetype và những tùy chỉnh cần làm trước khi phát triển sản phẩm thật.

## 2. Archetype thực sự là gì?

Một **archetype** là gói mẫu dự án mà Maven Archetype Plugin có thể đọc để sinh các thư mục/tệp và điền thông tin như tên dự án, package, phiên bản. Một mẫu có thể chứa:

- `pom.xml` với nhóm/artifact/phiên bản, dependency và plugin build;
- Cấu trúc source code Java, thư mục test và lớp ví dụ;
- Một số cấu hình Maven hoặc tài nguyên ban đầu;
- Biến tham số được thay vào nội dung tệp và đường dẫn khi tạo dự án.

Goal `archetype:generate` thuộc **Maven Archetype Plugin**. Nó là một *bước khởi tạo*; dự án được sinh ra trở thành mã nguồn của bạn, có thể sửa theo nhu cầu. Không cần gọi `archetype:generate` cho mỗi lần biên dịch hay chạy test.

So sánh:

| Việc làm | Lệnh điển hình | Kết quả |
| --- | --- | --- |
| Tạo bộ khung mới | `mvn archetype:generate` | Có dự án mới với `pom.xml`, `src/...` và các tệp mẫu |
| Biên dịch | `mvn compile` | Có class biên dịch ở `target/classes` |
| Chạy unit test | `mvn test` | Biên dịch test, chạy các test đã cấu hình |
| Đóng gói | `mvn package` | Thường có JAR/WAR tùy `packaging` |
| Xác minh build | `mvn verify` | Chạy lifecycle đến phase `verify`, gồm các kiểm tra đã cấu hình |

**Archetype không phải framework runtime hoặc dependency mà Java application phải import.** Sau khi tạo xong, `pom.xml`, code, test và mọi thay đổi về sau mới quyết định cách dự án được build.

Archetype đặc biệt hữu ích khi nhóm muốn các dự án mới có nền tảng tương tự nhau. Dù vậy, một mẫu “chạy được” chưa đồng nghĩa đã có đúng thiết kế, bảo mật, test và quy trình phát hành cho mọi bài toán.

## 3. Chuẩn bị trước khi chạy lệnh

Bạn cần JDK 17 trở lên, Maven có thể chạy từ terminal và kết nối đến repository khi Maven phải tải plugin/archetype ở lần đầu. Ví dụ dùng **Apache Maven Quickstart Archetype phiên bản 1.5**; mẫu này có cấu hình phù hợp với Java 17 và JUnit Jupiter.

Kiểm tra môi trường:

```bash
java -version
javac -version
mvn -version
```

Chú ý **`mvn -version` hiển thị JDK mà Maven đang thực sự chạy**. Nếu bạn vừa cài JDK 17 nhưng Maven vẫn trỏ vào JDK cũ, cần kiểm tra `JAVA_HOME` và `PATH`. Trên Windows, PowerShell, CMD hoặc shell của IDE có thể nhận môi trường khác nhau.

Hãy đứng trong một thư mục **cha** dành cho các dự án học tập. Chẳng hạn `projects/` là nơi bạn muốn có thư mục con `first-maven-app/`. Không cần tạo sẵn một POM hoặc một dự án Maven ở thư mục con.

## 4. Sinh dự án bằng `maven-archetype-quickstart`

### 4.1. Lệnh tạo dự án đầy đủ

Chạy nguyên **một dòng** dưới đây tại thư mục cha. Đặt mỗi đối số `-D...` trong dấu ngoặc kép giúp tránh một số vấn đề phân tích đối số của PowerShell trên Windows, đồng thời dùng được trong nhiều shell thông dụng:

```bash
mvn archetype:generate "-DarchetypeGroupId=org.apache.maven.archetypes" "-DarchetypeArtifactId=maven-archetype-quickstart" "-DarchetypeVersion=1.5" "-DgroupId=com.example" "-DartifactId=first-maven-app" "-Dversion=1.0-SNAPSHOT" "-Dpackage=com.example.first" "-DjavaCompilerVersion=17" "-DinteractiveMode=false"
```

Sau khi lệnh thành công, Maven tạo thư mục `first-maven-app/` ngay dưới nơi bạn đang đứng. Lần đầu có thể thấy Maven tải plugin và các artifact từ repository. Dòng `BUILD SUCCESS` tại bước **generate** chỉ xác nhận việc **tạo bộ khung** đã thành công; cần chạy phase test/build riêng để biết mã mẫu hoạt động.

Archetype cụ thể ở đây là `org.apache.maven.archetypes:maven-archetype-quickstart:1.5`. Chỉ rõ version rất hữu ích khi làm tài liệu cho người học: dự án không vô tình thay đổi vì một phiên bản archetype khác. Đặc biệt, `javaCompilerVersion` là tham số mà **quickstart 1.5 hỗ trợ**; không được coi là tham số chung cho mọi archetype.

### 4.2. Giải thích các tham số và hai nhóm tọa độ

| Tham số | Vai trò |
| --- | --- |
| `archetypeGroupId=org.apache.maven.archetypes` | Nhóm phát hành **archetype** |
| `archetypeArtifactId=maven-archetype-quickstart` | Tên artifact của **archetype** |
| `archetypeVersion=1.5` | Phiên bản **archetype** |
| `groupId=com.example` | Nhóm định danh của **dự án mới** |
| `artifactId=first-maven-app` | Tên artifact và thường là tên thư mục dự án |
| `version=1.0-SNAPSHOT` | Phiên bản của **dự án mới** |
| `package=com.example.first` | Java package dùng khi sinh mã nguồn/test |
| `javaCompilerVersion=17` | Đặt mức Java biên dịch của mẫu quickstart 1.5 |
| `interactiveMode=false` | Không hỏi người dùng từng giá trị trong quá trình sinh |

Ba giá trị `groupId:artifactId:version` thường gọi là **GAV**. Bài này có hai GAV độc lập:

- **Archetype:** `org.apache.maven.archetypes:maven-archetype-quickstart:1.5` — dùng làm khuôn.
- **Dự án được sinh:** `com.example:first-maven-app:1.0-SNAPSHOT` — định danh artifact sau này của dự án bạn.

`package=com.example.first` không nhất thiết phải bằng `groupId=com.example`. Nó quyết định câu lệnh `package com.example.first;` trong Java và đường dẫn thư mục tương ứng `com/example/first`. Trong thực tế, nên đặt tên package có quy tắc nhất quán để giảm nhầm lẫn.

### 4.3. Vì sao có chế độ tương tác và không tương tác?

Nếu chạy chỉ:

```bash
mvn archetype:generate
```

Maven Archetype Plugin có thể hiện danh mục mẫu, hỏi người dùng chọn archetype, nhập GAV, package và xác nhận. Cách này thích hợp để khám phá các mẫu mới nhưng khó hướng dẫn kết quả thống nhất hoặc tích hợp vào script tự động.

Với `-DinteractiveMode=false`, bạn cung cấp trước các thuộc tính cần thiết. Nếu archetype đòi hỏi thuộc tính bổ sung chưa có giá trị mặc định, lệnh có thể báo thiếu tham số; cần đọc lỗi và bổ sung thay vì nghĩ rằng mọi archetype đều dùng chung đúng một danh sách tùy chọn.

Ngoài quickstart còn có archetype cho plugin Maven, web application hoặc mẫu do tổ chức tự phát hành. **Chọn đúng mẫu theo mục đích**, vì mẫu Java console không tự có REST API, framework Spring Boot hoặc cấu hình vận hành sản phẩm.

## 5. Đọc cấu trúc được sinh và vai trò của từng tệp

Với quickstart 1.5 và `package=com.example.first`, phần chính của bộ khung có dạng:

```text
first-maven-app/
├── .mvn/
│   ├── jvm.config
│   └── maven.config
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/
    │           └── example/
    │               └── first/
    │                   └── App.java
    └── test/
        └── java/
            └── com/
                └── example/
                    └── first/
                        └── AppTest.java
```

**Những phần quan trọng cần phân biệt:**

- **`pom.xml`:** tệp Project Object Model, mô tả danh tính dự án, dependency, phiên bản, thuộc tính và công việc Maven phải thực hiện.
- **`src/main/java`:** nơi đặt mã Java được build thành chương trình/thư viện. `App.java` là lớp ví dụ, có thể đổi tên và thay bằng code nghiệp vụ.
- **`src/test/java`:** nơi đặt mã kiểm thử. `AppTest.java` là ví dụ test, giúp khởi động thói quen chạy test từ đầu.
- **`.mvn/maven.config`:** nơi có thể thiết lập tùy chọn Maven mặc định theo dự án. **`.mvn/jvm.config`** dành cho tùy chọn JVM chạy Maven. Đừng nhầm hai tệp này với Maven Wrapper; wrapper có thêm script/tệp riêng.
- **`src/main/resources` và `src/test/resources`:** những thư mục *theo quy ước* cho tài nguyên ứng dụng/test khi cần, dù quickstart có thể chưa tạo sẵn thư mục rỗng.

Câu lệnh `package com.example.first;` và vị trí `com/example/first` có liên hệ trực tiếp. Nếu đổi package trong source, bạn phải cập nhật test, import, đường dẫn và tên lớp khi chạy ở những nơi liên quan.

### 5.1. Tại sao chưa thấy `target/`?

Archetype tạo **mã nguồn và cấu hình đầu vào**. Khi chạy `mvn compile`, `mvn test` hoặc `mvn package`, Maven mới tạo kết quả trung gian và artifact dưới `target/`, chẳng hạn:

```text
first-maven-app/
└── target/
    ├── classes/
    ├── test-classes/
    ├── surefire-reports/
    └── first-maven-app-1.0-SNAPSHOT.jar
```

`target/classes` chứa lớp chính đã biên dịch; `target/test-classes` chứa lớp test; `target/surefire-reports` chứa kết quả test khi Surefire được chạy; file JAR xuất hiện khi đóng gói thành công. Đây là **đầu ra được sinh**, thường không đưa vào Git. Nội dung cụ thể có thể khác nhau tùy phase và plugin.

### 5.2. Minh họa đường đi từ archetype đến sản phẩm build

```text
Quickstart archetype 1.5
        |
        v
mvn archetype:generate
        |
        v
pom.xml + src/main/java + src/test/java + .mvn
        |
        v
Bạn sửa source, test và cấu hình POM
        |
        v
mvn clean verify
        |
        v
Compile -> Unit test -> Package -> Verify
        |
        v
target/classes + test reports + JAR
```

`App.java` và `AppTest.java` **không phải tên lớp Maven bắt buộc**. Đó là hai lớp minh họa của template. Điều quan trọng hơn là tuân thủ cấu trúc nguồn/test và cung cấp cấu hình plugin/dependency đúng.

## 6. Hiểu `pom.xml` được sinh ra

Trong POM, ba trường thể hiện danh tính dự án có nội dung tương đương:

```xml
<groupId>com.example</groupId>
<artifactId>first-maven-app</artifactId>
<version>1.0-SNAPSHOT</version>
```

Đây chỉ là **đoạn trích**, không phải toàn bộ `pom.xml` có thể dùng độc lập. POM thực cần thẻ gốc `<project>`, `modelVersion` và những cấu hình thích hợp do archetype tạo.

Những vùng đáng đọc khi mới mở POM:

1. **GAV và `packaging`:** xác định artifact sẽ build. Với project thông thường, `packaging` mặc định là `jar` nếu không khai báo.
2. **`properties`:** chứa các thuộc tính như phiên bản Java, encoding, phiên bản phụ thuộc hoặc biến cấu hình dùng chung.
3. **`dependencies`:** khai báo thư viện cần cho mã chính hoặc test. Quickstart 1.5 dùng JUnit Jupiter cho test; dependency có `test` scope thường không thuộc classpath runtime của ứng dụng.
4. **`build/plugins`:** khai báo plugin trực tiếp cho build; **`pluginManagement`** quản lý phiên bản/cấu hình plugin (không phải mọi plugin đặt ở đây đều tự chạy nếu chưa được dùng bởi lifecycle hoặc khai báo thích hợp).

Bộ khung tránh việc viết POM từ số không, nhưng vẫn phải đánh giá dependency, plugin, Java release, repository và yêu cầu ứng dụng trước khi dùng lâu dài. `javaCompilerVersion=17` giúp định hướng Java đầu ra của **mẫu 1.5**, không tự cài JDK 17 và không làm JDK cũ biên dịch được Java 17.

Mẫu có thể chứa metadata hoặc tệp gợi ý chưa phù hợp sản phẩm. Hãy hiểu trước khi sửa, nhất là khi thay GAV hay package vì các thay đổi này tác động tới tên artifact và tên lớp đầy đủ khi chạy.

## 7. Bài thực hành Java 17: sửa code mẫu, chạy test và JAR

Thực hiện trên dự án vừa sinh. Thay hoàn toàn nội dung **hai tệp** dưới đây; mỗi code block là một file Java độc lập ở đường dẫn được nêu. Quickstart 1.5 đã có JUnit Jupiter cho các unit test mẫu.

### 7.1. Tệp `src/main/java/com/example/first/App.java`

```java
package com.example.first;

public final class App {
    private App() {
    }

    public static String greeting() {
        return "Hello from Maven!";
    }

    public static void main(String[] args) {
        System.out.println(greeting());
    }
}
```

Lớp `App` có phương thức `greeting()` để test giá trị trả về và `main()` để in kết quả. Đây là chương trình Java 17 hợp lệ; thực tế code này cũng không cần các tính năng riêng của Java 17, nhưng dự án được định cấu hình build với mức Java 17.

### 7.2. Tệp `src/test/java/com/example/first/AppTest.java`

```java
package com.example.first;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void greetingReturnsExpectedText() {
        assertEquals("Hello from Maven!", App.greeting());
    }
}
```

`@Test` đến từ JUnit Jupiter; `assertEquals(expected, actual)` xác nhận kết quả thực bằng chuỗi mong đợi. Tên `AppTest` khớp cách Maven Surefire thường tìm test. Package của test cùng package với source nên có thể gọi `App.greeting()`.

### 7.3. Build và chạy từ thư mục đúng

Tại **thư mục cha** đang chứa `first-maven-app/`:

```bash
cd first-maven-app
mvn clean verify
java -cp target/first-maven-app-1.0-SNAPSHOT.jar com.example.first.App
```

Sau `mvn clean verify` thành công, mã chính và test đã được biên dịch, test đã chạy, JAR được tạo và lifecycle đi đến phase `verify`. Điều này giả định dependency/plugin có thể tải được và cấu hình của archetype không bị chỉnh sai.

**Đầu ra chính xác của lệnh Java cuối cùng**:

```text
Hello from Maven!
```

Không mô phỏng một stdout cố định cho toàn bộ `mvn clean verify`: Maven in thông tin plugin, kết quả test, tổng thời gian và thông báo download tùy môi trường. Bạn có thể xem báo cáo unit test dưới `target/surefire-reports/`.

**Vì sao dùng `java -cp ... com.example.first.App`?** JAR mặc định của ví dụ không nhất thiết có `Main-Class` trong manifest để chạy bằng `java -jar`. `-cp` nêu rõ nơi chứa class, sau đó chỉ định tên class đầy đủ. Với chương trình có dependency runtime bên ngoài JDK, cần bổ sung classpath hoặc cấu hình cách đóng gói phù hợp, không giả định một JAR cơ bản đã chứa mọi dependency.

Để hiểu các phase: `mvn test` biên dịch và chạy unit test; `mvn package` đi qua các phase trước nó (thường bao gồm test) rồi đóng gói; `mvn verify` đi đến phase verify với những kiểm tra đã cấu hình; `mvn clean verify` dọn đầu ra cũ trước khi build lại. `generate` và `verify` giải quyết hai việc khác nhau.

## 8. Bộ khung giúp gì, và những gì vẫn cần tự quyết định?

Bộ khung mang lại **một cách bắt đầu thống nhất**:

- Người mới biết đặt mã chính ở đâu, đặt test ở đâu và build bằng lệnh nào.
- IDE và Maven hiểu cùng một cấu trúc, ít phải tự ghép classpath hay tạo quy tắc biên dịch thủ công.
- `pom.xml` tập trung cấu hình nên người khác có thể mở dự án và chạy build mà không cần sao chép JAR bằng tay.
- Có sẵn test mẫu nên dễ tạo thói quen kiểm chứng thay đổi.
- Với mẫu chung của nhóm, có thể khởi tạo dự án theo quy ước tổ chức.

Nhưng **archetype không thể quyết định thay người phát triển** cách chia package nghiệp vụ, phạm vi unit/integration test, kiến trúc ứng dụng, cơ chế deploy, kiểm soát bảo mật và lựa chọn phiên bản thư viện. Sau khi sinh dự án, hãy:

1. Đổi code ví dụ thành chức năng thật, bổ sung test có ý nghĩa.
2. Chỉnh tên GAV/package cho đúng tổ chức ngay từ đầu; nếu đổi sau khi đã có mã, phải sửa mọi import và tên lớp liên quan.
3. Rà soát/cố định phiên bản plugin, dependency và Java release phù hợp; kiểm tra bảo mật và license.
4. Thiết lập Maven Wrapper khi cần thống nhất phiên bản Maven giữa máy cá nhân/CI; wrapper không tự cài hoặc đồng bộ JDK.
5. Thêm README dự án, Git ignore cho `target/`, CI và cấu hình môi trường khi có nhu cầu.
6. Đừng tự sinh đè lên thư mục dự án đã có nhiều thay đổi; tạo dự án mới ở nơi phù hợp rồi chủ động nhập nội dung nếu cần.

Với một ứng dụng Spring Boot, archetype quickstart là **mẫu Java nhỏ**, không tự cấu hình Spring Boot, starter, REST API hay ứng dụng server. Chọn công cụ khởi tạo hoặc archetype chuyên dụng nếu mục tiêu thật sự là Spring Boot, rồi hiểu POM và các lớp được sinh.

## 9. Các lỗi thường gặp và cách nhận biết

| Dấu hiệu | Cách xác định/khắc phục |
| --- | --- |
| `mvn` không được nhận diện | Kiểm tra Maven/`PATH` hoặc wrapper; xác minh bằng `mvn -version` |
| `mvn -version` hiển thị sai JDK | Kiểm tra `JAVA_HOME` và terminal/IDE thực tế đang dùng |
| `Could not resolve artifact` hay lỗi tải Archetype Plugin | Kiểm tra mạng, Maven Central hoặc mirror, proxy và tọa độ mẫu/phiên bản |
| Plugin vẫn hỏi thông tin | Kiểm tra `-DinteractiveMode=false` và các tham số bắt buộc khác |
| Shell Windows xử lý sai tham số `-D...` | Bọc từng tham số bằng ngoặc kép như ví dụ và chạy trên một dòng |
| Không tìm thấy project sau khi sinh | Kiểm tra thư mục đang đứng trước khi gọi lệnh; dự án nằm dưới tên `artifactId` |
| `The goal ... requires a project` khi chạy build | Đã `cd` vào thư mục chứa `pom.xml` chưa? |
| `invalid target release: 17` | Kiểm tra JDK thật sự trong `mvn -version` và Java target của POM |
| Không thấy `target/` sau generate | Phải chạy `mvn compile`, `mvn test` hoặc `mvn package/verify` |
| Test trong IDE chạy nhưng Maven không nhận | Kiểm tra đường dẫn `src/test/java`, tên `AppTest`, JUnit Jupiter, Surefire và báo cáo test |
| `ClassNotFoundException` | Xác minh package, tên class đầy đủ, `target/classes` hoặc JAR được chọn |
| `no main manifest attribute` với `java -jar` | Chưa thiết lập entry point trong manifest; dùng `java -cp` hoặc cấu hình plugin phù hợp |
| Tạo lại gặp thư mục trùng | Không sinh đè lên source đã sửa; chọn `artifactId` hoặc thư mục cha khác |

Khi có lỗi, hãy đọc phần cuối log Maven và nguyên nhân đầu tiên liên quan. Không nên xóa toàn bộ `~/.m2/repository`, bỏ qua test hoặc tắt kiểm tra bảo mật chỉ vì một lần download hay build thất bại.

## 10. Tự kiểm tra và bài tập mở rộng

**Bài tập 1 — giải thích bộ khung.** Sau khi tạo dự án, tìm và mô tả `pom.xml`, `App.java`, `AppTest.java`, `.mvn/`, rồi chỉ ra vì sao `target/` xuất hiện sau build. Viết lại GAV của **archetype** và GAV của **dự án** để thấy chúng khác nhau.

**Bài tập 2 — thay đổi có kiểm chứng.** Sửa `greeting()` thành một chuỗi khác, cập nhật assertion tương ứng trong `AppTest`, chạy `mvn clean verify` và chạy `App` từ JAR. Đầu ra phải khớp chuỗi mới.

**Bài tập 3 — quan sát test thất bại.** Tạm đổi giá trị expected trong `AppTest` thành `"Wrong text"`, chạy `mvn test` và đọc báo cáo; sau đó sửa lại. Bài tập giúp bạn phân biệt “sinh bộ khung thành công” và “mã hiện tại vượt qua kiểm thử”.

**Câu hỏi tự đánh giá:**

- Khi nào cần gọi lại `archetype:generate`, và khi nào chỉ cần `mvn test/package/verify`?
- Vì sao lệnh có hai nhóm tham số `archetypeArtifactId` và `artifactId`?
- Tệp nào mô tả cách build, thư mục nào chứa source, thư mục nào chứa đầu ra?
- Tại sao bộ khung có `AppTest.java` nhưng không đủ để khẳng định ứng dụng tương lai đã được kiểm thử đầy đủ?
- Khi đổi `package`, bạn phải kiểm tra những đường dẫn, import và lệnh chạy nào?

Nếu thực hiện được các bài tập và giải thích các câu hỏi, bạn đã hiểu vai trò đúng của archetype: **tạo điểm khởi đầu nhất quán cho dự án Maven**, rồi tự sở hữu và phát triển bộ khung đó bằng lifecycle Maven, mã nguồn và kiểm thử thực tế.

### Tài liệu chính thức

- [Maven in 5 Minutes — Quickstart 1.5 và cách build](https://maven.apache.org/guides/getting-started/maven-in-five-minutes.html)
- [Maven Quickstart Archetype — cấu trúc và các tham số riêng](https://maven.apache.org/archetypes/maven-archetype-quickstart/)
- [Introduction to Archetypes — khái niệm và các bộ mẫu](https://maven.apache.org/guides/introduction/introduction-to-archetypes.html)
- [Create a Project from an Archetype — Batch Mode](https://maven.apache.org/archetype/maven-archetype-plugin/specification/generate.html)
- [Introduction to the Build Lifecycle — phase/goal](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
