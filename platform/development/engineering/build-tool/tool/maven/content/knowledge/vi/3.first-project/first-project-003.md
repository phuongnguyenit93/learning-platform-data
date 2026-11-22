# Chọn tọa độ, package và phiên bản cho dự án Maven mới

## 1. Mục tiêu: đặt tên đúng trước khi viết mã

Khi bắt đầu một dự án Maven, các tên ban đầu không chỉ để hiển thị. Chúng quyết định cách Maven nhận diện artifact, tên file được đóng gói, nơi artifact nằm trong repository và cách mã Java được tổ chức. Đổi một tên sau khi dự án đã được nhiều người dùng có thể làm gián đoạn import, dependency hoặc quy trình phát hành.

Sau bài này, bạn có thể:

- Chọn **tọa độ Maven** gồm `groupId`, `artifactId` và `version` cho một dự án mới.
- Phân biệt **Java package** (`package vn.acme.training.orders;`) với **Maven packaging** (`<packaging>jar</packaging>`).
- Đặt tên package, thư mục mã nguồn và lớp Java khớp nhau.
- Quyết định khi nào dùng `-SNAPSHOT` và khi nào tạo bản release.
- Viết một `pom.xml` nhỏ, build JAR bằng Maven và tự kiểm chứng các lựa chọn đặt tên.

Ví dụ xuyên suốt: nhóm giả định **Acme** muốn làm ứng dụng console quản lý đơn hàng bằng Java 17. Đây là tên minh họa; với dự án thật, hãy dùng namespace được tổ chức cho phép.

## 2. Năm khái niệm dễ bị lẫn

| Thành phần | Ví dụ của dự án | Ý nghĩa thực tế |
| --- | --- | --- |
| `groupId` | `vn.acme.training` | Namespace của nhóm/tổ chức phát hành artifact. |
| `artifactId` | `order-console` | Tên riêng của artifact trong nhóm. |
| `version` | `0.1.0-SNAPSHOT` | Phiên bản của artifact được tạo hoặc tiêu thụ. |
| **Java package** | `vn.acme.training.orders` | Không gian tên của các lớp Java; xuất hiện trong khai báo `package` và đường dẫn source. |
| **Maven packaging** | `jar` | Kiểu artifact và các binding mặc định khi đóng gói. |

Ba giá trị đầu tạo **GAV** (*Group, Artifact, Version*):

```text
vn.acme.training:order-console:0.1.0-SNAPSHOT
       groupId       artifactId         version
```

GAV là cách gọi tắt khi cần nhận diện dependency. Khi phân biệt nhiều dạng đóng gói, Maven còn dùng `type` (thường là `jar`) và đôi khi `classifier`. Ví dụ thư viện phụ thuộc phổ biến nhất sử dụng `groupId`, `artifactId`, `version` và mặc định type `jar`.

Điều quan trọng: **`groupId` không phải `package` của một lớp Java**, **`artifactId` không phải tên lớp `main`**, và **`version` của artifact không phải phiên bản JDK hay Maven**. Chúng có thể được đặt nhất quán để dễ hiểu nhưng phục vụ các mục đích khác nhau.

## 3. Chọn `groupId`: ai sở hữu không gian tên?

`groupId` phân nhóm artifact theo tổ chức, dự án hoặc sản phẩm. Quy ước phổ biến là đảo các thành phần của một domain bạn quản lý:

```text
Domain do tổ chức quản lý: training.acme.vn
Namespace đề xuất:         vn.acme.training
```

Ví dụ lựa chọn phù hợp:

- Công ty có namespace `vn.acme` và dự án phục vụ đào tạo: `vn.acme.training`.
- Nhóm đã có namespace chung `com.company.platform`: module mới tiếp tục dùng namespace này nếu được đội ngũ duyệt.
- Dự án cá nhân có domain riêng: chọn namespace dẫn xuất từ domain ấy, hoặc theo quy định của repository nơi định phát hành.

**Lưu ý:** đoạn `vn.acme.training` chỉ là ví dụ giả định. Sở hữu domain/namespace cần phù hợp thực tế; tự đặt `org.apache.maven` hay `com.google` không biến bạn thành chủ sở hữu của namespace đó. Repository công khai có thể yêu cầu xác minh namespace khi phát hành. Một POM có thể dùng `groupId` bất kỳ trong build local, nhưng như vậy **không chứng minh quyền phát hành công khai** dưới `groupId` ấy.

Các tiêu chí thực hành:

1. Dùng namespace ổn định và có chủ sở hữu rõ ràng.
2. Nhất quán cách viết chữ thường và dấu chấm giữa các thành phần.
3. Không gắn phiên bản, ngày tháng hoặc tên môi trường (`dev`, `prod`) vào `groupId` chỉ để phân biệt mỗi lần build; những thứ này có cơ chế riêng.
4. Không đổi `groupId` tùy hứng khi artifact đã được dự án khác tham chiếu: thay đổi khiến người dùng phải cập nhật dependency coordinates.

`groupId` có thể trùng tiền tố Java package để dễ tìm mã nguồn, nhưng **Maven không bắt buộc** hai giá trị giống hệt nhau. Tránh dùng dấu gạch ngang trong các thành phần mà bạn cũng dự định tái sử dụng làm Java package, bởi Java package không chấp nhận dấu `-`.

## 4. Chọn `artifactId`: dự án tạo ra artifact gì?

`artifactId` là định danh của artifact bên trong `groupId`. Nó thường phản ánh **chức năng** hoặc **vai trò** của module, không nhất thiết phản ánh tên công ty.

| Mục đích | Gợi ý `artifactId` | Vì sao |
| --- | --- | --- |
| Ứng dụng console xử lý đơn hàng | `order-console` | Ngắn, chỉ rõ phạm vi và hình thức chạy. |
| Thư viện quy tắc đơn hàng | `order-core` | Phân biệt thư viện dùng lại với ứng dụng. |
| Adapter kết nối cơ sở dữ liệu | `order-persistence` | Mô tả trách nhiệm kỹ thuật của module. |
| API của dịch vụ đơn hàng | `order-api` | Dễ nhận biết hợp đồng/API. |

Quy ước tốt cho dự án mới: chữ thường, các từ ngăn cách bằng dấu gạch ngang, không khoảng trắng hoặc ký tự đặc biệt, tên đủ cụ thể để phân biệt với các module cùng nhóm. Maven không ép buộc mọi `artifactId` phải theo một kiểu đặt tên duy nhất; mục tiêu là nhất quán và dễ bảo trì.

Trong ví dụ:

```xml
<groupId>vn.acme.training</groupId>
<artifactId>order-console</artifactId>
```

`artifactId` này sẽ ảnh hưởng đến tên file JAR mặc định:

```text
target/order-console-0.1.0-SNAPSHOT.jar
```

Tên file mặc định hình thành từ `artifactId` và `version`. Có thể tùy chỉnh `<finalName>` trong `<build>`, nhưng **đổi tên file không đổi GAV** mà Maven dùng để nhận diện artifact.

Phân biệt thêm:

- `<name>Order Console</name>`: tên mô tả có thể có khoảng trắng, dùng cho con người, báo cáo và trang dự án; **không thay thế** `artifactId`.
- `<description>...`: phần mô tả văn bản, không thay đổi coordinates.
- Java class `App` hoặc `OrderApplication`: tên lớp Java; không cần trùng `artifactId`.

## 5. Chọn Java `package`: mã nguồn thuộc không gian tên nào?

Từ khóa `package` của Java tổ chức lớp và tránh xung đột tên. Với ví dụ này, chọn base package:

```java
package vn.acme.training.orders;
```

Tệp có package trên nên đặt tại:

```text
src/main/java/vn/acme/training/orders/App.java
```

Đường dẫn tương ứng cấu trúc package giúp Maven và IDE tìm mã nguồn đúng quy ước. Tên file của lớp `public class App` phải là `App.java`.

Quy tắc đặt tên Java package:

- Dùng các thành phần viết thường, tách bằng dấu chấm: `vn.acme.training.orders`.
- Mỗi thành phần phải là **Java identifier hợp lệ**; không có dấu gạch ngang, dấu cách hoặc ký tự mở đầu bằng chữ số. Tránh Java keywords (`class`, `package`, `int`...).
- Ưu tiên tên dựa trên domain/namespace tổ chức sở hữu để giảm khả năng trùng.
- Chọn theo **miền trách nhiệm mã nguồn**, không buộc phải sao chép nguyên `artifactId`. `order-console` là Maven artifactId hợp lệ nhưng `package vn.acme.training.order-console;` là cú pháp Java **sai**.
- Khi tách package con, có thể dùng `vn.acme.training.orders.service`, `...model`, `...cli` theo nhu cầu. Dự án rất nhỏ chưa cần tự tạo nhiều tầng rỗng.

Một dự án có thể chứa nhiều Java package. Ngược lại, nhiều Maven module có thể có các Java package liên quan. Vì vậy **một Maven artifact không đồng nghĩa đúng một Java package**. Java package được dùng trong `import`, tên lớp đầy đủ (*fully qualified class name*) và cơ chế truy cập trong Java.

Ví dụ hai lớp cùng tên trong package khác nhau vẫn khác danh tính:

```text
vn.acme.training.orders.App
vn.acme.training.billing.App
```

Bạn cần đổi Java package khi trách nhiệm mã nguồn đổi hoặc khi sắp xếp lại API. Với thư viện đã công bố, đổi package public có thể làm người dùng phải sửa `import` và mã nguồn. Chỉ thay `groupId`/`artifactId` trong POM không tự động refactor package của các lớp.

## 6. Chọn `packaging`: Maven phải tạo loại đầu ra nào?

Trong Maven POM, `packaging` trả lời “dự án được build thành loại artifact nào?”. Đây **không phải** keyword `package` của Java:

| `<packaging>` | Dùng cho | Đầu ra/vai trò |
| --- | --- | --- |
| `jar` | Thư viện Java, ứng dụng console hoặc một module JVM đóng gói JAR | Tạo file `.jar`, dùng các goal mặc định liên quan đến JAR. |
| `war` | Ứng dụng web theo cấu trúc WAR truyền thống | Tạo file `.war`, có binding tương ứng với WAR. |
| `pom` | POM cha, POM aggregator, BOM | Chủ yếu chứa metadata/cấu hình; không tự tạo JAR của mã Java. |

Nếu bỏ `<packaging>`, Maven mặc định sử dụng `jar`. Với ứng dụng console đầu tiên, khai báo `<packaging>jar</packaging>` rõ ràng giúp người học thấy sự lựa chọn. Các packaging mở rộng có thể được plugin cung cấp; không nên đoán rằng Maven hỗ trợ mọi chuỗi tùy ý.

**JAR không tự động có khả năng chạy bằng `java -jar`.** Cần entry point trong manifest (chẳng hạn `Main-Class`), và ứng dụng có dependency runtime bên ngoài còn cần cách cung cấp classpath/đóng gói phù hợp. Ở ví dụ bên dưới ta cấu hình Maven JAR Plugin để thêm `Main-Class`; lớp ứng dụng chỉ dùng JDK nên có thể chạy trực tiếp.

## 7. Chọn `version`: bản đang phát triển hay bản phát hành?

`version` xác định một phiên bản của artifact: cùng `groupId` và `artifactId` nhưng khác `version` là **hai tọa độ khác nhau**. Maven không tự hiểu phiên bản ứng dụng như thông số biên dịch Java.

Với dự án mới, một quy ước dễ đọc là `MAJOR.MINOR.PATCH`:

| Ví dụ | Ý nghĩa theo quy ước nhóm |
| --- | --- |
| `0.1.0-SNAPSHOT` | Bản phát triển đầu tiên đang thay đổi thường xuyên. |
| `0.1.0` | Bản 0.1.0 ổn định theo mức cam kết của nhóm. |
| `0.1.1` | Bản sửa lỗi tương thích theo quy ước nhóm. |
| `0.2.0` | Bản thêm tính năng theo quy ước nhóm. |
| `1.0.0` | Mốc API/sản phẩm ổn định do nhóm quyết định. |
| `2.0.0` | Thường thể hiện thay đổi không tương thích nếu nhóm áp dụng Semantic Versioning. |

**Đây là chính sách đặt phiên bản mà đội ngũ lựa chọn, không phải quy tắc Maven tự bảo đảm.** Maven cho phép nhiều dạng version/qualifier và có cơ chế so sánh phiên bản riêng. Không nên giả định Maven tự kiểm tra một thay đổi có phá tương thích API hay không.

### Snapshot khác release thế nào?

`0.1.0-SNAPSHOT` là bản đang phát triển: một repository hỗ trợ snapshot có thể chứa các bản build liên tiếp của cùng version logic và metadata cập nhật để chọn bản phù hợp. Tại các kho remote, snapshot thường được gắn timestamp/build number để quản lý các lần xuất bản. Vì vậy kết quả resolve snapshot có thể đổi theo thời gian và chính sách cập nhật.

`0.1.0` (không có `-SNAPSHOT`) thường được coi là bản release. Thực hành tốt là **giữ release bất biến**: khi muốn sửa, tăng version rồi phát hành artifact mới.

Chọn chiến lược đơn giản cho dự án đầu tiên:

1. Trong giai đoạn làm thử và thay đổi liên tục: `0.1.0-SNAPSHOT`.
2. Khi muốn chốt mốc dùng thử/đưa cho người dùng: build, test và phát hành `0.1.0` (không snapshot).
3. Với thay đổi tiếp theo: chuyển sang `0.1.1-SNAPSHOT` hoặc `0.2.0-SNAPSHOT` tùy chính sách; không liên tục ghi đè release cũ.
4. Nếu module đã là dependency của đội khác, công bố thay đổi version rõ ràng và thống nhất compatibility.

Không nhầm `version` của artifact với ba thứ sau:

- `mvn -version` hiển thị **phiên bản Maven** và JDK đang chạy Maven.
- `<maven.compiler.release>17</maven.compiler.release>` chỉ định **mức Java API/bytecode** được compile (cần JDK tương thích).
- `<modelVersion>4.0.0</modelVersion>` là **phiên bản mô hình POM**, không phải artifact version.

Đừng dùng version động như `LATEST`/`RELEASE` hoặc khoảng version tùy tiện cho build cần tái lập; pin các dependency và plugin quan trọng theo chính sách dự án.

## 8. Ví dụ hoàn chỉnh: tạo dự án Java 17 từ năm lựa chọn

Giả sử dự án là console app đơn giản không có thư viện ngoài. Chốt trước bộ tên:

```text
groupId     = vn.acme.training
artifactId  = order-console
version     = 0.1.0-SNAPSHOT
package     = vn.acme.training.orders
packaging   = jar
Java target = 17
main class  = vn.acme.training.orders.App
```

Cấu trúc thư mục:

```text
order-console/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/
                └── acme/
                    └── training/
                        └── orders/
                            └── App.java
```

**File `pom.xml`** đặt ở gốc `order-console/`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.acme.training</groupId>
    <artifactId>order-console</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Order Console</name>
    <description>Vi du ung dung Maven dau tien</description>

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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.acme.training.orders.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Cấu hình plugin ở trên đặt phiên bản cụ thể và cấu hình `Main-Class` để JAR có thể chạy bằng `java -jar`. Dự án không dùng thư viện bên ngoài nên chưa cần khai `<dependencies>`. Các plugin build vẫn có thể được Maven tải từ repository khi chạy lần đầu.

**File `src/main/java/vn/acme/training/orders/App.java`:**

```java
package vn.acme.training.orders;

public final class App {
    private App() {
        // Không cần tạo instance cho ứng dụng console này.
    }

    public static void main(String[] args) {
        System.out.println("Order console ready");
    }
}
```

Dòng `package` khớp với đường dẫn source. Tên `App` khớp với `App.java` và khớp đuôi của `<mainClass>` trong POM. Không cần đặt lớp là `OrderConsole` chỉ vì `artifactId` tên `order-console`.

### Build và chạy

Yêu cầu: có JDK 17+ và Maven tương thích trong `PATH`. Kiểm tra:

```bash
java -version
mvn -version
```

Trong thư mục `order-console` có `pom.xml`, chạy:

```bash
mvn clean package
java -jar target/order-console-0.1.0-SNAPSHOT.jar
```

Khi Maven build thành công và bạn chạy dòng `java -jar`, **stdout của chương trình** là:

```text
Order console ready
```

Log Maven phụ thuộc môi trường, Maven/plugins/cache nên có thể khác; không coi toàn bộ log console là output cố định của `App.main`.

Mối liên hệ cần nhận ra:

1. Maven đọc `groupId`, `artifactId`, `version` và `packaging` từ POM.
2. Compiler Plugin biên dịch lớp Java theo package; các file `.class` nằm dưới `target/classes/vn/acme/training/orders/`.
3. JAR Plugin đóng gói file `target/order-console-0.1.0-SNAPSHOT.jar` và ghi `Main-Class: vn.acme.training.orders.App` vào manifest.
4. `java -jar` đọc manifest để xác định điểm vào; chương trình in một dòng.
5. Nếu chạy `mvn install`, Maven đưa artifact và metadata liên quan vào **local repository**, ví dụ `~/.m2/repository/vn/acme/training/order-console/0.1.0-SNAPSHOT/`. Đường dẫn repository dựa trên GAV, không dựa trên Java package `...orders`.

### Kiểm chứng sau khi chọn tên

- Mở `pom.xml`: GAV trùng giá trị dự định chưa?
- Mở `App.java`: package, đường dẫn và public class có nhất quán chưa?
- Kiểm tra tên file trong `target/`: `order-console-0.1.0-SNAPSHOT.jar` đã được tạo từ build hiện tại chưa?
- Chạy `java -jar`: manifest có main class đúng và output khớp không?
- Khi cần kiểm tra mô hình đã hợp nhất từ parent/config, dùng `mvn help:effective-pom`. Nếu dự án mới độc lập không có parent tùy chỉnh, nhiều giá trị vẫn được Maven bổ sung từ mặc định.

## 9. Quyết định đặt tên trong dự án nhiều module

Giả sử sau này hệ thống thêm thư viện core và ứng dụng API. Có thể giữ namespace tổ chức nhưng dùng `artifactId` khác:

| Module | `groupId` | `artifactId` | Java base package |
| --- | --- | --- | --- |
| Thư viện nghiệp vụ | `vn.acme.training` | `order-core` | `vn.acme.training.orders.core` |
| API giao tiếp | `vn.acme.training` | `order-api` | `vn.acme.training.orders.api` |
| Ứng dụng console | `vn.acme.training` | `order-console` | `vn.acme.training.orders.cli` |

Đây là ví dụ **quy hoạch tên**, không yêu cầu bắt buộc phải tách module trong bài tập đầu tiên. Khi có parent POM/aggregator, mỗi module có POM riêng; `version` có thể được kế thừa từ parent tùy cách tổ chức. Không nhất thiết mỗi module có một `groupId` khác, và không cần đổi package chỉ để phản ánh tên file JAR.

Đối với **thư viện** có người khác dùng, tọa độ ổn định rất quan trọng: consumer sẽ khai phụ thuộc bằng `groupId/artifactId/version`. Với **ứng dụng** chỉ chạy nội bộ, bạn vẫn nên dùng quy ước nhất quán để dễ build, tra artifact và theo dõi release.

## 10. Sai lầm phổ biến và cách sửa

### Sai lầm 1: dùng `artifactId` làm Java package nguyên xi

Sai:

```java
package vn.acme.training.order-console;
```

Dấu `-` không hợp lệ trong Java identifier. Chọn `package vn.acme.training.orders;` hoặc `...orderconsole;`. Không cần đổi `artifactId=order-console` chỉ vì package phải viết khác.

### Sai lầm 2: dùng một giá trị “version” cho mọi thứ

`<version>0.1.0-SNAPSHOT</version>` là phiên bản **artifact**; `<maven.compiler.release>17</maven.compiler.release>` là mức **Java**. Thay app version không nâng Java, và nâng Java release không tự tăng app version.

### Sai lầm 3: nhầm tên hiển thị với tọa độ

`<name>Order Console</name>` giúp con người đọc thông tin, nhưng dependency của project khác cần `<artifactId>order-console</artifactId>`. Sửa `name` không đổi coordinate hay tên file mặc định.

### Sai lầm 4: nghĩ `packaging=jar` tự tạo file chạy được

JAR mặc định có thể là **library JAR**, không có `Main-Class`; khi đó `java -jar` có thể báo thiếu entry point. Ví dụ của bài có manifest và không có dependency runtime bên ngoài nên chạy được. Với ứng dụng lớn cần phụ thuộc, phải thiết kế classpath hoặc công cụ đóng gói thích hợp.

### Sai lầm 5: phát hành lại cùng một release version

Việc ghi đè `1.0.0` ở remote repository có thể dẫn đến người dùng nhận artifact khác nhau với cùng tọa độ, gây mất khả năng tái lập build. Hãy tăng version khi phát hành thay đổi và giữ release bất biến theo chính sách repository.

### Sai lầm 6: đổi GAV rồi nghĩ Maven sẽ sửa toàn bộ mã nguồn

Đổi `groupId`/`artifactId`/`version` trong POM không tự động sửa các `package`, `import` hoặc FQCN trong code. Ngược lại, đổi package bằng IDE refactor không tự đổi tọa độ artifact. Kiểm tra cả hai khi đổi tên dự án.

### Sai lầm 7: chọn `groupId` không có quyền kiểm soát

Sao chép namespace của tổ chức lớn từ bài hướng dẫn có thể chạy được local nhưng không phù hợp cho phát hành thật. Hãy dùng namespace thuộc dự án/tổ chức, hoặc namespace được kho artifact chấp nhận và xác minh.

## 11. Checklist trước khi tạo repository cho dự án mới

1. **Ai là người sở hữu?** Chọn `groupId` ổn định theo namespace tổ chức.
2. **Artifact làm gì?** Chọn `artifactId` cụ thể, dễ tìm, phân biệt với module khác.
3. **Đã cần release chưa?** Chọn `0.1.0-SNAPSHOT` khi đang phát triển; bỏ `-SNAPSHOT` và phát hành version ổn định khi đã qua kiểm thử và được chấp thuận.
4. **Java code thuộc miền nào?** Chọn base package hợp lệ, nhất quán, rồi đặt source đúng đường dẫn.
5. **Build thành gì?** Chọn `jar` cho console/library thông thường, `war` cho dự án web tương ứng, `pom` cho parent/aggregator/BOM.
6. **Java target bao nhiêu?** Khai `maven.compiler.release` theo baseline runtime và JDK đang dùng; đừng nhầm với artifact version.
7. **Có cần `java -jar`?** Nếu có, cấu hình manifest và xử lý dependency runtime phù hợp.
8. **Có người dùng artifact chưa?** Nếu có, cân nhắc tác động khi đổi GAV hoặc public Java package, và chuẩn hóa phiên bản/phát hành.

Đối với dự án đầu tiên, cấu hình **`vn.acme.training:order-console:0.1.0-SNAPSHOT`**, Java package **`vn.acme.training.orders`**, packaging **`jar`** là một ví dụ nhất quán. Điều cần ghi nhớ là **GAV nhận diện artifact trong Maven repository; Java package nhận diện lớp; packaging quyết định loại đầu ra; Java release quyết định môi trường biên dịch**. Mỗi lựa chọn phục vụ một mục đích và cần được kiểm chứng riêng.

## Tham khảo chính thức

- [Apache Maven: POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven: Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven: Maven Coordinates](https://maven.apache.org/guides/mini/guide-naming-conventions.html)
- [Apache Maven: Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Compiler Plugin: Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven JAR Plugin: Make The Jar Executable](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html)
