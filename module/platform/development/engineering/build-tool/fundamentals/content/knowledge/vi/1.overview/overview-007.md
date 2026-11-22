# Quy ước thay cho cấu hình và vai trò của cấu trúc dự án

Khi xây dựng một ứng dụng Java, build tool cần biết mã nguồn nằm ở đâu, tài nguyên nào phải được đưa vào classpath, mã kiểm thử nào cần biên dịch và kết quả build sẽ được lưu ở đâu. Nếu mỗi dự án phải khai báo tường minh tất cả những thông tin này, cấu hình sẽ dài, lặp lại và khó thống nhất giữa các nhóm.

Các build tool giải quyết vấn đề đó bằng **quy ước thay cho cấu hình** (*Convention over Configuration*). Thay vì yêu cầu lập trình viên mô tả lại những điều phổ biến, công cụ và plugin cung cấp một bộ mặc định đã được thống nhất. Cấu trúc thư mục của dự án trở thành một phần của cách build tool hiểu dự án: đặt mã nguồn đúng vị trí theo quy ước thường đã đủ để công cụ tự tìm và xử lý nó.

## 1. Vì sao build tool cần quy ước?

Một quy trình build Java thường phải thực hiện nhiều việc:

- Tìm các tệp mã nguồn cần biên dịch.
- Phân biệt mã nguồn ứng dụng với mã nguồn kiểm thử.
- Tìm tài nguyên như tệp cấu hình, mẫu HTML, ảnh hoặc dữ liệu tĩnh.
- Xác định thư viện phụ thuộc cần có trên classpath.
- Chạy các bước biên dịch, kiểm thử và đóng gói theo đúng thứ tự.
- Lưu lớp đã biên dịch và sản phẩm cuối cùng vào thư mục đầu ra.

Nếu không có quy ước, mỗi dự án có thể chọn một cách tổ chức khác nhau. Dự án A đặt mã nguồn trong `source/`, dự án B đặt trong `java/`, còn dự án C chia mã nguồn theo một cấu trúc riêng. Khi đó, mỗi dự án phải khai báo các đường dẫn tương ứng. Người mới tham gia cũng phải học cách cấu hình riêng của từng dự án trước khi có thể hiểu quy trình build.

Quy ước tạo ra một điểm chung. Khi một dự án tuân theo cấu trúc được công cụ hỗ trợ, build tool có thể suy ra phần lớn thông tin cần thiết từ vị trí tệp và loại plugin đã áp dụng. Cấu hình chỉ cần tập trung vào những điểm thực sự khác biệt.

## 2. Convention over Configuration là gì?

**Convention over Configuration** là cách thiết kế trong đó hệ thống cung cấp các quy tắc và giá trị mặc định hợp lý cho những trường hợp phổ biến. Người sử dụng chỉ cần khai báo thêm khi muốn thay đổi hành vi mặc định.

Ví dụ, với một dự án Java thông thường, plugin Java của Gradle mặc định tìm mã nguồn chính trong `src/main/java` và mã nguồn kiểm thử trong `src/test/java`. Nếu dự án sử dụng đúng các thư mục này, bạn không cần liệt kê từng thư mục trong build script.

Quy trình có thể hình dung như sau:

```text
Build file và plugin
        |
        v
Các quy ước mặc định được áp dụng
        |
        v
Build tool xác định mã nguồn, tài nguyên và mã kiểm thử
        |
        v
Biên dịch -> Kiểm thử -> Đóng gói
        |
        v
Sản phẩm được ghi vào thư mục đầu ra
```

Điều này không có nghĩa là dự án không còn cấu hình. Build tool vẫn cần cấu hình cho những quyết định riêng như phiên bản Java, thư viện phụ thuộc, tên artifact, plugin bổ sung hoặc đường dẫn tùy chỉnh. Điểm khác biệt là các thông tin phổ biến đã có mặc định, nên dự án không phải khai báo lại chúng.

### Lợi ích của quy ước

**Giảm cấu hình lặp lại.** Nhiều dự án Java có cùng cách bố trí mã nguồn. Build script có thể ngắn hơn vì không phải khai báo lại các đường dẫn chuẩn.

**Tạo tính nhất quán.** Thành viên trong nhóm có thể tìm mã nguồn, tài nguyên và kiểm thử ở những vị trí quen thuộc. Việc đọc dự án khác cũng dễ dàng hơn.

**Giúp công cụ phối hợp tốt hơn.** Build tool, IDE, hệ thống CI và các plugin thường cùng hiểu những cấu trúc phổ biến. Khi dự án tuân theo quy ước, các công cụ có thể nhận diện nội dung mà ít cần cấu hình bổ sung.

**Giảm chi phí bảo trì.** Khi một dự án dùng cấu trúc chuẩn, việc thay đổi máy phát triển hoặc đưa dự án lên CI thường ít phụ thuộc vào những đường dẫn riêng do từng người tự đặt.

### Đổi lại, cần hiểu quy ước

Quy ước chỉ hữu ích khi nhóm biết công cụ đang mong đợi điều gì. Nếu đặt tệp ở vị trí khác với mặc định mà không khai báo lại, build tool có thể bỏ qua tệp đó. Vì vậy, khi một tệp không được biên dịch, không được đóng gói hoặc không xuất hiện trên classpath, cần kiểm tra cả vị trí tệp lẫn cấu hình source set/resource trước khi kết luận rằng mã nguồn bị lỗi.

## 3. Cấu trúc thư mục Java phổ biến

Một dự án Java đơn giản có thể được tổ chức như sau:

```text
my-app/
├── pom.xml                 # Cấu hình dự án Maven
├── build.gradle            # Hoặc build.gradle.kts nếu dùng Gradle
├── settings.gradle         # Cấu hình dự án Gradle, đặc biệt khi có nhiều module
└── src/
    ├── main/
    │   ├── java/           # Mã nguồn ứng dụng
    │   └── resources/      # Tài nguyên ứng dụng
    └── test/
        ├── java/           # Mã nguồn kiểm thử
        └── resources/      # Tài nguyên dành cho kiểm thử
```

Trong một dự án thực tế, thường chỉ có build file của công cụ đang sử dụng. `pom.xml` thuộc Maven; `build.gradle` hoặc `build.gradle.kts` thuộc Gradle. `settings.gradle` là tệp cấu hình cấp gốc của Gradle và đặc biệt quan trọng trong build nhiều project.

### `src/main/java`: mã nguồn chính

Đây là nơi đặt mã Java tạo nên chức năng của ứng dụng. Các thư mục con thường phản ánh tên package.

Ví dụ:

```text
src/main/java/com/example/shop/ProductService.java
```

Nội dung tệp:

```java
package com.example.shop;

public class ProductService {
    public String getName() {
        return "Notebook";
    }
}
```

`src/main/java` là **source root**. Phần đường dẫn bên dưới source root tương ứng với package `com.example.shop`; tên package không bao gồm `src.main.java`. Khi build, công cụ tìm các tệp Java trong source root, biên dịch chúng và tạo các tệp `.class` trong thư mục đầu ra.

### `src/main/resources`: tài nguyên của ứng dụng

Thư mục này chứa các tệp không phải mã Java nhưng cần có khi ứng dụng chạy, chẳng hạn:

```text
src/main/resources/
├── application.yml
├── messages.properties
└── templates/
    └── welcome.html
```

Các tệp này thường được sao chép vào vùng tài nguyên trên classpath khi build. Vì vậy, nếu `application.yml` nằm trực tiếp trong `src/main/resources`, ứng dụng có thể truy cập nó bằng tên tài nguyên `application.yml`, thay vì phải đưa cả đường dẫn `src/main/resources` vào tên tài nguyên.

Tách tài nguyên khỏi mã Java giúp build tool xử lý đúng hai loại đầu vào: mã Java cần biên dịch và tài nguyên cần sao chép hoặc đóng gói.

### `src/test/java`: mã nguồn kiểm thử

Đây là nơi đặt các lớp kiểm thử. Ví dụ:

```text
src/test/java/com/example/shop/ProductServiceTest.java
```

Mã kiểm thử thường sử dụng thư viện kiểm thử như JUnit. Build tool biên dịch mã kiểm thử với classpath phù hợp, sau đó giao việc thực thi cho test runner được cấu hình trong dự án.

Mã trong `src/test/java` không được xem là mã nguồn chính để đóng gói vào artifact ứng dụng thông thường. Việc tách riêng giúp sản phẩm chính không chứa lớp kiểm thử và giúp build tool áp dụng các phụ thuộc kiểm thử đúng phạm vi.

### `src/test/resources`: tài nguyên dành cho kiểm thử

Thư mục này chứa dữ liệu chỉ cần khi chạy kiểm thử, ví dụ tệp JSON mẫu, dữ liệu CSV, cấu hình kiểm thử hoặc dữ liệu giả lập. Những tệp này được đưa vào classpath kiểm thử, không phải tài nguyên chạy chính của ứng dụng.

### Thư mục đầu ra của build

Thư mục đầu ra chứa các tệp được tạo trong quá trình build. Tên thư mục phụ thuộc vào công cụ:

| Công cụ | Thư mục đầu ra mặc định thường gặp | Ví dụ nội dung |
|---|---|---|
| Maven | `target/` | `target/classes`, `target/test-classes`, tệp JAR |
| Gradle | `build/` | `build/classes`, `build/resources`, tệp JAR |

Đây là dữ liệu được tạo ra, không phải nơi đặt mã nguồn do lập trình viên duy trì. Khi cần kiểm tra kết quả build, hãy tìm trong thư mục đầu ra tương ứng. Khi sửa mã nguồn, hãy sửa trong các source root của dự án.

## 4. Build tool sử dụng cấu trúc dự án như thế nào?

Cấu trúc thư mục chỉ có ý nghĩa với build tool khi công cụ hoặc plugin áp dụng các quy ước tương ứng. Một thư mục có tên `src/main/java` tự nó không thực hiện việc biên dịch; plugin Java của Gradle hoặc các quy tắc mặc định của Maven mới là thành phần diễn giải vị trí đó.

### Với Maven

Maven sử dụng `pom.xml` làm mô tả dự án. Với dự án Java có cách bố trí chuẩn, Maven nhận diện các thư mục mã nguồn và tài nguyên theo cấu trúc mặc định. Các bước trong vòng đời build được gắn với những mục tiêu plugin phù hợp, chẳng hạn biên dịch mã nguồn chính, biên dịch mã kiểm thử, chạy kiểm thử và đóng gói artifact.

Một POM tối giản có thể khai báo danh tính dự án như sau:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
    <version>1.0.0</version>
</project>
```

Với cấu trúc thư mục chuẩn, không cần khai báo lại `src/main/java` và `src/test/java` trong POM. Khi chạy một vòng đời build phù hợp, Maven sử dụng các thư mục mặc định để tìm đầu vào và lưu kết quả trong `target/`.

### Với Gradle

Gradle có thể thực hiện nhiều loại build khác nhau. Đối với dự án Java, plugin `java` bổ sung các source set, task và quy ước thư mục dành cho mã nguồn chính, mã nguồn kiểm thử và tài nguyên.

Ví dụ build script Groovy:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'
```

Sau khi áp dụng plugin Java, Gradle mặc định nhận diện:

- `src/main/java` cho mã nguồn chính.
- `src/main/resources` cho tài nguyên chính.
- `src/test/java` cho mã nguồn kiểm thử.
- `src/test/resources` cho tài nguyên kiểm thử.

Plugin cũng tạo các task quen thuộc như `compileJava`, `processResources`, `compileTestJava`, `test` và `jar`. Các task có quan hệ phụ thuộc, nên khi yêu cầu một task ở giai đoạn sau, Gradle có thể chạy những task đầu vào cần thiết trước đó.

Với plugin Java, một số đường dẫn đầu ra thường gặp là:

```text
build/
├── classes/java/main/       # Lớp đã biên dịch của ứng dụng
├── classes/java/test/       # Lớp đã biên dịch của kiểm thử
├── resources/main/          # Tài nguyên chính đã xử lý
└── libs/                    # Artifact được đóng gói, ví dụ JAR
```

Điểm cần nhớ là quy ước thư mục Java ở đây được cung cấp bởi plugin Java. Nếu dự án Gradle không áp dụng plugin này hoặc dùng plugin có mô hình đầu vào khác, không nên mặc định rằng mọi quy ước của dự án Java đều tự động tồn tại.

## 5. Cấu trúc dự án giúp tổ chức trách nhiệm

Một cấu trúc dự án tốt không chỉ giúp build tool tìm tệp. Nó còn thể hiện cách nhóm phân chia nội dung và trách nhiệm.

**Phân biệt mã chạy và mã kiểm thử.** Người đọc có thể nhận ra phần nào thuộc sản phẩm, phần nào phục vụ xác minh hành vi. Build tool cũng có thể áp dụng classpath và phụ thuộc phù hợp cho từng phần.

**Phân biệt mã Java và tài nguyên.** Tệp `.java` được biên dịch; tệp cấu hình, mẫu và dữ liệu được xử lý như tài nguyên. Đặt chúng đúng source root giúp quá trình đóng gói và truy cập lúc chạy nhất quán.

**Tạo ranh giới giữa các module.** Trong build nhiều project, mỗi module có thể sở hữu mã nguồn, tài nguyên, kiểm thử và build file riêng. Ranh giới này giúp khai báo phụ thuộc giữa các phần của hệ thống rõ ràng hơn.

**Giúp IDE và CI hiểu dự án.** IDE thường nhận diện source root, test source root và resource root từ build model. CI chạy cùng build tool có thể dùng các quy ước đó để build trên máy khác mà không cần người chạy tự chỉ từng tệp.

**Giữ đầu vào và đầu ra tách biệt.** Mã nguồn do con người duy trì nằm trong cây `src/`; sản phẩm trung gian và kết quả build nằm trong `target/` hoặc `build/`. Sự phân biệt này giúp tránh sửa nhầm tệp sinh ra và giúp việc làm sạch đầu ra an toàn, có mục đích.

## 6. Vai trò của cấu trúc trong build nhiều project

Khi ứng dụng lớn hơn, một build có thể gồm nhiều project hoặc module. Mỗi module có thể đại diện cho một phần có trách nhiệm riêng, ví dụ `app`, `domain` hoặc `infrastructure`.

Với Gradle, `settings.gradle` ở thư mục gốc khai báo những project tham gia build. Ví dụ:

```groovy
rootProject.name = 'commerce'
include 'app', 'domain', 'infrastructure'
```

Cấu trúc thư mục thường tương ứng với khai báo trên:

```text
commerce/
├── settings.gradle
├── build.gradle
├── app/
│   ├── build.gradle
│   └── src/main/java/
├── domain/
│   ├── build.gradle
│   └── src/main/java/
└── infrastructure/
    ├── build.gradle
    └── src/main/java/
```

Ở đây, thư mục gốc mô tả build tổng thể; mỗi thư mục con được khai báo là một Gradle subproject. Build tool có thể cấu hình chung ở cấp gốc và cấu hình riêng ở từng module. Các module có thể phụ thuộc lẫn nhau theo quan hệ được khai báo trong build script.

Không nên suy luận rằng cứ có một thư mục con là build tool tự động coi đó là module. Với Gradle, danh sách project thuộc build được xác định bởi `settings.gradle` và các quy tắc liên quan. Một thư mục có thể chỉ là thư mục chứa tài liệu, script hoặc tài nguyên mà không phải project độc lập.

Maven cũng hỗ trợ build nhiều module. Trong mô hình đó, POM cấp gốc thường dùng packaging `pom` và khai báo các module con trong phần `<modules>`. Dù cú pháp khác nhau, mục đích vẫn là làm rõ project gốc, các module thành viên và quan hệ giữa chúng.

## 7. Khi nào cần thay đổi quy ước mặc định?

Nên giữ cấu trúc chuẩn khi nó đáp ứng được nhu cầu của dự án. Tuy nhiên, có những trường hợp cần cấu hình bổ sung:

- Dự án cũ đã có cấu trúc thư mục riêng và việc di chuyển mã nguồn gây ảnh hưởng lớn.
- Mã nguồn được sinh tự động nằm trong một thư mục riêng.
- Dự án có thêm nhóm kiểm thử đặc biệt như integration test.
- Một module cần nhiều source directory hoặc nhiều loại tài nguyên.
- Build nhiều project có cấu trúc vật lý khác với ánh xạ mặc định.

Khi thay đổi, cần khai báo rõ cho build tool biết vị trí mới. Ví dụ, nếu muốn bổ sung mã Java được sinh tự động vào source set `main` của Gradle, có thể thêm thư mục như sau:

```groovy
sourceSets {
    main {
        java {
            srcDir 'src/generated/java'
        }
    }
}
```

`srcDir` thêm một thư mục vào danh sách source directory hiện có. Cách này giữ lại thư mục mặc định `src/main/java` và bổ sung `src/generated/java`.

Với Maven, có thể thay đổi thư mục mã nguồn chính và kiểm thử trong phần `build` của POM:

```xml
<build>
    <sourceDirectory>source/java</sourceDirectory>
    <testSourceDirectory>checks/java</testSourceDirectory>
</build>
```

Ví dụ trên thay đổi vị trí Maven dùng để tìm mã nguồn chính và mã nguồn kiểm thử. Khi cấu hình đường dẫn tùy chỉnh, cần bảo đảm các thành viên trong nhóm, IDE và CI đều sử dụng cùng build model. Nếu chỉ đổi tên thư mục trên ổ đĩa mà không cập nhật cấu hình, công cụ vẫn tiếp tục tìm ở vị trí mặc định.

Không nên khai báo lại mọi đường dẫn chuẩn chỉ để làm build script trông đầy đủ hơn. Cấu hình thừa khiến người đọc phải phân biệt đâu là mặc định, đâu là quyết định riêng của dự án, đồng thời tăng số chỗ cần cập nhật khi thay đổi cấu trúc.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `src/main/java` là package gốc của mọi lớp | Đây là source root; package bắt đầu từ các thư mục con bên dưới nó. |
| Đặt tệp ở bất kỳ đâu thì build tool cũng tự tìm thấy | Công cụ chỉ quét các source directory và resource directory đã được cấu hình hoặc quy ước hỗ trợ. |
| `src/test/java` là một phần của mã nguồn chạy chính | Đây là source set kiểm thử, được biên dịch và chạy theo cấu hình kiểm thử. |
| `target/` hoặc `build/` là nơi lưu mã nguồn | Đây là các thư mục đầu ra do build tạo ra. |
| Gradle luôn tự nhận mọi thư mục con là module | Project thành viên được khai báo trong cấu hình settings hoặc được ánh xạ theo quy tắc tương ứng. |
| Convention over Configuration có nghĩa là không cần build script | Build script vẫn khai báo plugin, phụ thuộc và các lựa chọn riêng; quy ước chỉ giảm phần cấu hình lặp lại. |

Một lỗi thực tế thường gặp là chuyển `ProductService.java` từ `src/main/java` sang `source/java` nhưng không cập nhật source set. Tệp vẫn tồn tại và nội dung Java vẫn hợp lệ, nhưng build tool không đưa tệp vào quá trình biên dịch. Tương tự, đặt `application.yml` trong một thư mục không được khai báo làm resource directory có thể khiến ứng dụng không tìm thấy cấu hình khi chạy.

Khi gặp lỗi kiểu này, hãy kiểm tra theo thứ tự: build root có đúng không, plugin cần thiết đã được áp dụng chưa, source set/resource directory đang trỏ đến đâu, và tệp có thực sự nằm trong các thư mục đó không.

## 9. Cách đọc cấu trúc một dự án mới

Khi mở một dự án Java chưa quen thuộc, có thể lần lượt xác định các điểm sau:

1. **Tìm build file ở thư mục gốc.** `pom.xml` thường cho biết dự án dùng Maven; `build.gradle` hoặc `build.gradle.kts` cho biết dự án dùng Gradle.
2. **Xác định plugin hoặc loại project.** Với Gradle, xem các plugin được áp dụng để biết quy ước nào đang có hiệu lực. Với Maven, xem packaging và cấu hình trong POM.
3. **Tìm source root và resource root.** Bắt đầu từ các thư mục chuẩn như `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources`.
4. **Kiểm tra cấu hình ghi đè.** Tìm các khai báo source set, source directory, resource directory hoặc cấu hình module để biết dự án có thay đổi mặc định hay không.
5. **Xác định thư mục đầu ra.** Maven thường dùng `target/`; Gradle thường dùng `build/`. Đây là nơi kiểm tra lớp đã biên dịch và artifact.
6. **Nếu là build nhiều project, kiểm tra cấu hình cấp gốc.** Với Gradle, xem `settings.gradle` để biết các project được đưa vào build; với Maven, xem phần khai báo module trong POM gốc.

Ví dụ, nếu thấy một lớp Java trong `app/src/main/java/com/example/App.java`, hãy đọc đường dẫn theo từng lớp: `app` có thể là module, `src/main/java` là source root theo quy ước Java, còn `com.example` là package của lớp. Cách đọc này giúp phân biệt cấu trúc build, cấu trúc thư mục và cấu trúc package thay vì xem chúng là một khái niệm duy nhất.

## 10. Tình huống áp dụng

Giả sử bạn nhận một dự án Gradle có cấu trúc:

```text
sample/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/Hello.java
    │   └── resources/greeting.txt
    └── test/
        └── java/com/example/HelloTest.java
```

Build script áp dụng plugin Java:

```groovy
plugins {
    id 'java'
}
```

Không cần khai báo riêng các đường dẫn trong cấu trúc trên. Plugin Java nhận diện `Hello.java` là mã nguồn chính, `greeting.txt` là tài nguyên chính và `HelloTest.java` là mã kiểm thử. Khi chạy task `test`, Gradle xây dựng các đầu vào cần thiết, biên dịch mã chính và mã kiểm thử, rồi chạy kiểm thử theo cấu hình của dự án.

Giả sử nhóm chuyển `Hello.java` sang `source/com/example/Hello.java` nhưng giữ nguyên build script. Plugin Java không tự suy ra rằng `source/` là thư mục mới. Để build tiếp tục nhận diện lớp này, nhóm phải hoặc đưa tệp về `src/main/java`, hoặc cấu hình source set để thêm `source` vào danh sách mã nguồn chính.

Tình huống này cho thấy cấu trúc thư mục và cấu hình build gắn với nhau như thế nào: quy ước giúp dự án hoạt động với ít cấu hình; khi dự án rời khỏi quy ước, cấu hình cần mô tả phần thay đổi để build tool tiếp tục xử lý đúng đầu vào.
