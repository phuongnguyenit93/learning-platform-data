# Đọc log một lượt build Maven thành công và lỗi đầu tiên

## Mục tiêu của bài học

Khi chạy `mvn clean package`, Maven đọc `pom.xml`, xác định dự án và các plugin cần dùng, lần lượt chạy những goal gắn với các pha của vòng đời build, rồi in kết quả. Log là chuỗi bằng chứng cho biết **Maven đang chạy đến đâu**, **bước nào thành công hoặc thất bại** và **đâu là lỗi cụ thể đầu tiên có thể sửa**.

Trong bài này, ta tự tạo một dự án Java 17 bằng Maven, đọc một lượt `BUILD SUCCESS`, cố ý gây một lỗi Java, đọc lượt `BUILD FAILURE` và sửa lỗi. Các khối log là **trích đoạn minh họa đã chọn lọc**, nên không bao gồm tất cả dòng xuất ra; đường dẫn hệ thống, thời gian, số lượng bản tải và một số phiên bản plugin có thể khác giữa các máy.

## 1. Chuẩn bị một dự án Maven nhỏ

Cần JDK 17+ và Maven chạy được từ terminal. Nếu dự án có Maven Wrapper, có thể dùng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows) thay cho `mvn`. Trong bài này, các lệnh minh họa dùng `mvn`.

Kiểm tra công cụ:

```bash
java -version
mvn -version
```

Trong kết quả `mvn -version`, chú ý **Java version** và **Java home**: đó là JDK mà tiến trình Maven đang dùng; nó có thể khác JDK bạn nghĩ đang cấu hình.

Cấu trúc thư mục:

```text
first-maven/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── Hello.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>first-maven</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/Hello.java`:

```java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Maven!");
    }
}
```

Tệp và tên public class đều là `Hello`; package `example` khớp vị trí `src/main/java/example/`. Cấu hình `maven.compiler.release=17` yêu cầu đầu ra tương thích Java 17 nhưng **không cài JDK tự động**.

## 2. Lần build thành công: chạy lệnh và tìm các mốc chính

Từ thư mục chứa `pom.xml`, chạy:

```bash
mvn -B -ntp clean package
```

Giải thích: `-B` bật batch mode, phù hợp môi trường không tương tác; `-ntp` ẩn thanh tiến độ tải; `clean` chạy lifecycle làm sạch các sản phẩm trước đó; `package` chạy các pha cần thiết đến bước đóng gói. Với `packaging=jar`, Maven tạo JAR nếu toàn bộ các bước bắt buộc trong lần chạy đều thành công.

Các dòng tiêu biểu có thể trông như sau (đã bỏ những phần trung gian):

```text
[INFO] Scanning for projects...
[INFO] ------------------------< example:first-maven >------------------------
[INFO] Building first-maven 1.0-SNAPSHOT
[INFO] --------------------------------[ jar ]---------------------------------
[INFO] --- compiler:3.13.0:compile (default-compile) @ first-maven ---
[INFO] Compiling 1 source file with javac [debug release 17] to target/classes
[INFO] BUILD SUCCESS
```

Cách đọc:

1. **`Scanning for projects`**: Maven đang tìm POM và nạp thông tin dự án.
2. **`example:first-maven`**: tọa độ `groupId:artifactId`; kiểm tra ngay để tránh đọc log của sai dự án.
3. **`Building first-maven 1.0-SNAPSHOT`**: tên và phiên bản artifact sẽ được build.
4. **`[ jar ]`**: kiểu `packaging` của dự án; dòng này **chưa có nghĩa** JAR đã tạo xong.
5. **`compiler:3.13.0:compile (default-compile) @ first-maven`**: goal `compile` của Maven Compiler Plugin 3.13.0 đang chạy cho dự án `first-maven`.
6. **`Compiling 1 source file ... to target/classes`**: biên dịch một tệp Java và đặt bytecode vào `target/classes`.
7. **`BUILD SUCCESS`**: Maven hoàn tất lệnh vừa chạy mà không gặp lỗi khiến build dừng.

Trong một lần `package`, log thường có thêm các goal xử lý resources, biên dịch test, thực thi test và đóng JAR. Với dự án mẫu không có test, các thông báo như `No tests to run` hoặc `skip non existing resourceDirectory` **không phải lỗi**. Maven có thể cần tải plugin hoặc dependency ở lần chạy đầu; các dòng `Downloading from` và `Downloaded from` là tiến độ thông thường nếu tải thành công.

Sau build, theo quy ước Maven, kiểm tra:

- `target/classes/example/Hello.class`: kết quả của bước compile.
- `target/first-maven-1.0-SNAPSHOT.jar`: kết quả đóng gói JAR.

Chương trình Java **không tự chạy** trong lệnh `mvn clean package`. Để kiểm chứng `main`, chạy:

```bash
java -cp target/classes example.Hello
```

Stdout chính xác của chương trình:

```text
Hello, Maven!
```

Đừng nhầm dòng stdout của chương trình với dòng `BUILD SUCCESS` của Maven. JAR trong ví dụ cũng chưa khai báo `Main-Class` trong manifest, vì vậy `java -jar target/first-maven-1.0-SNAPSHOT.jar` không tự động là cách chạy phù hợp.

## 3. Cấu trúc log Maven cần nhận diện

| Loại dòng | Ví dụ | Ý nghĩa khi đọc |
| --- | --- | --- |
| Khởi đầu | `[INFO] Scanning for projects...` | Maven bắt đầu đọc dự án. |
| Nhận diện | `[INFO] Building first-maven 1.0-SNAPSHOT` | Đang thao tác trên artifact nào. |
| Plugin/goal | `[INFO] --- compiler:3.13.0:compile (default-compile) @ first-maven ---` | Đang xử lý bước cụ thể nào. |
| Thông tin | `[INFO] Compiling 1 source file` | Hoạt động bình thường; chưa phải kết luận cuối. |
| Cảnh báo | `[WARNING] ...` | Điều nên xem xét, nhưng không mặc nhiên làm build fail. |
| Chẩn đoán lỗi | `[ERROR] ...` | Đọc cả cụm lỗi và ngữ cảnh để tìm nguyên nhân. |
| Kết luận | `BUILD SUCCESS` hoặc `BUILD FAILURE` | Kết quả lần thực thi Maven. |

Dạng dòng goal:

```text
--- plugin-prefix:version:goal (execution-id) @ artifact-id ---
```

Phần prefix cho biết plugin, phiên bản cho biết phiên bản plugin, `goal` cho biết thao tác, `execution-id` cho biết lần gắn goal vào build, và `artifact-id` xác định module. Ví dụ `compiler:3.13.0:compile (default-compile) @ first-maven` là **biên dịch** trong project `first-maven`; lỗi sau dòng goal này gợi ý điều tra mã Java, JDK và compiler configuration.

**`BUILD SUCCESS` chỉ có nghĩa các bước thật sự đã được gọi đều thành công.** Nếu lệnh là `mvn compile`, nó không chứng minh test đã chạy hay JAR đã được đóng gói. Với `mvn package`, test có thể bị bỏ qua nếu dự án hoặc lệnh cấu hình bỏ qua test. Cũng đừng dùng `BUILD FAILURE` để kết luận ngay rằng nguồn Java sai: có thể lỗi là dependency, plugin, POM, JDK hoặc test.

## 4. Tạo lỗi biên dịch đầu tiên

Giữ nguyên `pom.xml`. Đổi nội dung `src/main/java/example/Hello.java` thành:

```java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println(missingName);
    }
}
```

Biến `missingName` chưa khai báo. Trong tệp đúng như trên, tên biến bắt đầu ở **dòng 5, cột 28** (cột tính từ 1). Chạy lại cùng một lệnh:

```bash
mvn -B -ntp clean package
```

Trích đoạn log kiểu thường gặp trên Linux; đường dẫn đầu có thể khác theo máy:

```text
[INFO] --- compiler:3.13.0:compile (default-compile) @ first-maven ---
[ERROR] COMPILATION ERROR :
[ERROR] /home/user/first-maven/src/main/java/example/Hello.java:[5,28] cannot find symbol
[ERROR]   symbol:   variable missingName
[ERROR]   location: class example.Hello
[INFO] BUILD FAILURE
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile (default-compile) on project first-maven: Compilation failure
```

Giải mã từ lỗi gốc:

- **Goal thất bại** là `compiler:compile`. Maven chưa thể đi tiếp để tạo artifact mới theo lần build này.
- **Tệp lỗi** là `Hello.java`; phần `[5,28]` chỉ dòng và cột nơi javac gặp ký hiệu không giải quyết được.
- **`cannot find symbol`**: trình biên dịch không nhận diện được ký hiệu ở vị trí đó.
- **`symbol: variable missingName`**: ký hiệu cụ thể là biến `missingName`.
- **`location: class example.Hello`**: ngữ cảnh lớp đang được biên dịch.
- **`Failed to execute goal ... Compilation failure`**: Maven tóm tắt việc plugin compiler thất bại. Đây không phải vị trí sửa cụ thể.
- **`BUILD FAILURE`**: kết luận của lần chạy, không phải chẩn đoán nguyên nhân.

Với cùng lỗi, một số phiên bản hoặc cấu hình có thể diễn đạt log hơi khác; điều quyết định vẫn là **tên tệp + vị trí + thông báo compiler**.

## 5. Quy trình tìm “lỗi đầu tiên” hiệu quả

Hãy phân biệt ba loại dòng thường bị coi là “lỗi đầu tiên”:

- **Tiêu đề lỗi**: `[ERROR] COMPILATION ERROR :` chỉ mở đầu một cụm chẩn đoán.
- **Nguyên nhân cụ thể**: `Hello.java:[5,28] cannot find symbol` kèm `variable missingName` là điều bạn có thể sửa.
- **Tổng kết lỗi**: `Failed to execute goal ...` và `BUILD FAILURE` nói lần chạy đã dừng, nhưng riêng chúng chưa đủ chỉ ra sửa ở đâu.

Thao tác thực tế theo thứ tự:

1. **Kiểm tra cuối log** xem `BUILD FAILURE` hay `BUILD SUCCESS`; ghi nhớ lệnh đã chạy.
2. Nếu fail, xác định goal/plugin đang chạy ngay trước khối chẩn đoán và dự án (`@ first-maven`) có đúng không.
3. **Đọc ngược lên vùng chẩn đoán**, rồi đọc từ trên xuống trong vùng đó để tìm dòng đầu tiên có thông tin trực tiếp: tệp/dòng/cột, tên artifact không resolve, test nào thất bại hoặc plugin nào ném exception.
4. Với nhiều dòng `[ERROR]` cùng một cụm, ghép chúng thành **một nguyên nhân đầy đủ**. Đừng đếm từng `[ERROR]` là một lỗi độc lập.
5. **Sửa một nguyên nhân hợp lý đầu tiên**, chạy lại cùng lệnh và đối chiếu kết quả. Một lỗi cú pháp ở trước có thể kéo theo nhiều lỗi phụ phía sau; sau khi sửa lỗi đầu tiên, danh sách lỗi có thể thay đổi.

“Lỗi đầu tiên” ở đây nghĩa là **chẩn đoán đầu tiên đủ cụ thể để hành động**, không phải dòng đầu tiên mang nhãn `[ERROR]`. Nếu lỗi xuất hiện trong dependency resolution trước bước compile, thì lỗi resolution có thể là thứ cần xử lý trước; không ép mọi `BUILD FAILURE` thành lỗi Java.

## 6. Sửa lỗi và chạy lại

Trong `Hello.java`, thay dòng gây lỗi bằng:

```java
System.out.println("Hello, Maven!");
```

Dòng trên **là đoạn thay thế bên trong `main`**, không phải chương trình Java độc lập. Cấu trúc chương trình đầy đủ vẫn giống mục 1. Chạy:

```bash
mvn -B -ntp clean package
java -cp target/classes example.Hello
```

Kết quả kỳ vọng: Maven in `BUILD SUCCESS`; lệnh `java` in `Hello, Maven!`. `clean` loại các sản phẩm build cũ trong thư mục `target`, vì vậy bạn tránh nhầm class/JAR được tạo bởi lần build trước với sản phẩm của lần chạy hiện tại.

Đối chiếu trước/sau:

| Đọc log | Khi thiếu `missingName` | Sau khi sửa |
| --- | --- | --- |
| Goal compile | Bắt đầu nhưng thất bại. | Chạy thành công. |
| Dòng chẩn đoán | `cannot find symbol` ở `Hello.java:[5,28]`. | Không còn lỗi này. |
| Kết quả cuối | `BUILD FAILURE`. | `BUILD SUCCESS`. |
| Bước tiếp theo | Mở mã nguồn và sửa biến chưa khai báo. | Kiểm tra artifact và chạy chương trình. |

Nếu build fail, một file JAR còn sót từ trước **không chứng minh** build hiện tại thành công; luôn đối chiếu trạng thái lần chạy và thời điểm tạo artifact.

## 7. Những lỗi khác và cách định vị trong log

| Dấu hiệu | Nhóm vấn đề | Điểm kiểm tra đầu tiên |
| --- | --- | --- |
| `Non-parseable POM`, `Malformed POM` | POM/XML không hợp lệ. | `pom.xml`, dòng/cột XML, thẻ và cấu trúc POM. |
| `Could not resolve dependencies`, `Could not find artifact` | Dependency/repository. | Tọa độ `groupId:artifactId:version`, mạng, mirror, proxy, credential, repository. |
| `release version 17 not supported` | JDK chạy Maven không hỗ trợ target release. | `mvn -version`, `JAVA_HOME`, toolchain/compiler. |
| `cannot find symbol` | Compiler không resolve biến, phương thức, class hoặc import. | Tệp, dòng/cột, định nghĩa và phạm vi truy cập. |
| `package ... does not exist` | Import/package hoặc dependency compile classpath. | Package/import và dependency được khai báo trong POM. |
| `Tests run: ..., Failures: ...` hoặc `There are test failures` | Test chạy nhưng thất bại. | Tên test, stack trace, `target/surefire-reports`. |
| `Unknown lifecycle phase` | Mục tiêu Maven không hợp lệ. | Chính tả pha/goal trên dòng lệnh. |
| `Failed to execute goal ...` | Plugin/goal thất bại (dòng tổng kết). | Đọc phần báo lỗi chi tiết **phía trên**. |

Đối với test, `Failures` thường là assertion không đúng, còn `Errors` thường là exception hoặc lỗi thực thi test. Kết quả cuối vẫn có thể là `BUILD FAILURE`.

Một `[WARNING]` không tự động là nguyên nhân gây fail. Ngược lại, một dòng `[ERROR]` rất dài ở cuối log thường chỉ là phần Maven tóm tắt, còn nguyên nhân hữu ích hơn nằm phía trên. Tránh xóa toàn bộ `~/.m2/repository` hoặc nâng phiên bản plugin theo phản xạ khi chưa xác định lỗi gốc.

## 8. Cách lưu log để tra cứu và chia sẻ

Khi log dài, nên giữ lại **lệnh chính xác** bạn đã dùng và lưu cả stdout/stderr. Với Bash:

```bash
mvn -B -ntp clean package > build.log 2>&1
```

Dấu `>` ghi đè file `build.log` của lần trước; dùng tên riêng cho mỗi lần nếu cần so sánh. Sau đó đọc log và tìm `BUILD FAILURE`, `[ERROR]`, `Failed to execute goal`, tên tệp Java hoặc tên artifact dependency; quan trọng nhất là **đọc các dòng xung quanh**, vì lỗi có thể trải trên nhiều dòng.

Trên PowerShell, khi dự án có Maven Wrapper, lệnh chạy tương ứng là:

```powershell
.\mvnw.cmd -B -ntp clean package
```

Nếu dự án không có Wrapper nhưng Maven đã cài, dùng `mvn -B -ntp clean package`. Hãy dùng đúng cú pháp shell đang làm việc.

Nếu chẩn đoán thông thường chưa đủ:

- `mvn -e clean package`: hiển thị stack trace giúp tìm lỗi trong Maven/plugin.
- `mvn -X clean package`: bật debug log chi tiết hơn; hữu ích với repository, dependency, classpath và cấu hình khó. Dùng khi cần vì log rất dài và có thể chứa thông tin môi trường nhạy cảm.
- `mvn -q clean package`: giảm log thường, **không phù hợp bài tập học trình tự build** vì nhiều dòng `[INFO]` bị ẩn.
- `mvn help:effective-pom`: xem cấu hình POM thực tế sau kế thừa/profile khi nghi lỗi cấu hình. Đây là goal riêng, không thay thế đọc nguyên nhân hiện tại.

Khi gửi lỗi cho đồng đội, nên kèm lệnh chạy, đoạn log từ goal thất bại qua các dòng chẩn đoán tới `BUILD FAILURE`, phiên bản Maven/JDK, tệp liên quan và những gì bạn đã thử. Không gửi secret có thể xuất hiện trong log debug.

## 9. Bài tập kiểm tra hiểu log

**Câu 1.** Log in `[WARNING]` và kết thúc `BUILD SUCCESS`. Build có fail không?  
**Đáp án:** Không. Lần build hoàn tất; vẫn cần xem warning có gây rủi ro trong tương lai hay không.

**Câu 2.** Thấy `[ERROR] Failed to execute goal ... Compilation failure` ở gần cuối, nhưng phía trên có `Hello.java:[5,28] cannot find symbol`. Nên sửa đâu?  
**Đáp án:** Mở `Hello.java` dòng 5, xem biến chưa khai báo; dòng `Failed to execute goal` chỉ là tổng kết.

**Câu 3.** `mvn compile` in `BUILD SUCCESS`. Có thể kết luận đã chạy hết test và đã tạo JAR mới không?  
**Đáp án:** Không. `compile` chỉ chạy tới pha compile của lifecycle mặc định.

**Câu 4.** Maven báo `release version 17 not supported` mặc dù Java hợp lệ. Hướng kiểm tra?  
**Đáp án:** Xem JDK Maven thực dùng qua `mvn -version`, `JAVA_HOME`, toolchain và cấu hình compiler.

**Câu 5.** `mvn clean package` in `BUILD SUCCESS`, nhưng terminal không xuất hiện `Hello, Maven!`. Vì sao?  
**Đáp án:** Maven build/đóng gói ứng dụng, không mặc định gọi `main`. Chạy `java -cp target/classes example.Hello`.

## Nguồn tham khảo

- [Apache Maven — Getting Started Guide](https://maven.apache.org/guides/getting-started/): ví dụ log build, cấu trúc dự án, `target/classes` và test.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): cách pha `compile`, `test`, `package`, `verify` liên hệ với plugin/goal.
- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html): `-B`, `-e`, `-X`, `-q` và các tùy chọn dòng lệnh khác.

Khi đọc một log Maven chưa quen: **kiểm tra dự án và lệnh → tìm plugin/goal đang chạy → xem BUILD SUCCESS/FAILURE → nếu fail, tìm thông điệp đầu tiên đủ cụ thể → sửa nguyên nhân → chạy lại cùng lệnh**.
