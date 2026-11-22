# Tọa độ Maven: `groupId`, `artifactId` và `version`

Maven cần một cách thống nhất để nhận diện project và các artifact được chia sẻ giữa nhiều project. Thay vì dựa vào tên file hoặc đường dẫn tùy ý trên máy lập trình viên, Maven dùng một bộ tọa độ để xác định chính xác artifact cần tạo, tải về, cài đặt hoặc sử dụng làm dependency.

Ba thành phần cốt lõi của tọa độ Maven là **`groupId`**, **`artifactId`** và **`version`**. Chúng thường được gọi chung là GAV. Khi đọc một POM hoặc khai báo dependency, cần hiểu từng thành phần đại diện cho điều gì, cách chúng kết hợp để tạo định danh duy nhất và cách Maven dùng định danh đó để tìm artifact trong repository.

## 1. Tọa độ Maven là gì?

Một tọa độ Maven cơ bản có dạng:

```text
groupId:artifactId:version
```

Ví dụ:

```text
com.example.orders:order-service:1.4.0
```

Có thể đọc tọa độ này như sau:

- `groupId = com.example.orders`: nhóm hoặc namespace sở hữu artifact.
- `artifactId = order-service`: tên artifact trong nhóm đó.
- `version = 1.4.0`: phiên bản cụ thể của artifact.

Mỗi thành phần giải quyết một phần của câu hỏi: artifact thuộc nhóm nào, tên gì và phiên bản nào. Chỉ dùng `artifactId` thường chưa đủ để phân biệt hai thư viện cùng tên do những tổ chức khác nhau phát hành. Thêm `groupId` xác định namespace; thêm `version` xác định bản phát hành cần sử dụng.

Trong POM, ba thành phần thường được khai báo ở cấp project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.orders</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0</version>
    <packaging>jar</packaging>
</project>
```

POM ở trên mô tả một project có tọa độ `com.example.orders:order-service:1.4.0`. Khi build và cài đặt hoặc deploy artifact, Maven sử dụng tọa độ này để định danh sản phẩm.

## 2. `groupId`: namespace của tổ chức hoặc nhóm project

`groupId` xác định nhóm sở hữu hoặc namespace mà artifact thuộc về. Quy ước phổ biến là dùng tên miền ngược, tương tự cách đặt package Java:

```text
com.example
com.example.platform
com.example.orders
org.apache.commons
org.springframework
```

Tên miền ngược giúp giảm nguy cơ trùng namespace giữa các tổ chức. Ví dụ, một tổ chức sở hữu `example.com` có thể dùng các group bắt đầu bằng `com.example` cho các artifact do mình phát hành.

### 2.1. Quy ước đặt groupId

Một `groupId` nên:

- Đại diện cho một tổ chức, sản phẩm hoặc nhóm project có quyền sở hữu rõ ràng.
- Có namespace ổn định theo thời gian.
- Dùng chữ thường và dấu chấm để phân cấp theo quy ước phổ biến.
- Tránh dùng tên quá chung như `utils`, `common` hoặc `library` nếu không có namespace bao quanh.

Ví dụ một tổ chức có thể phân chia:

```text
vn.acme.platform
vn.acme.platform.security
vn.acme.order
vn.acme.payment
```

Không bắt buộc `groupId` phải trùng package Java. Một artifact có thể chứa nhiều package, và package bên trong JAR có thể được tổ chức theo cấu trúc khác. `groupId` là định danh Maven, còn package Java là namespace của lớp ở cấp mã nguồn/bytecode.

### 2.2. `groupId` có thể được kế thừa

Nếu project khai báo một POM cha, `groupId` của project con có thể được kế thừa từ parent khi không khai báo lại. Ví dụ:

```xml
<!-- parent/pom.xml -->
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>2.0.0</version>
    <packaging>pom</packaging>
</project>
```

POM con:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.acme.platform</groupId>
        <artifactId>platform-parent</artifactId>
        <version>2.0.0</version>
    </parent>

    <artifactId>order-service</artifactId>
</project>
```

Project con có `groupId` là `vn.acme.platform` thông qua kế thừa parent. `artifactId` vẫn cần được xác định cho project con. Tọa độ hiệu lực của module là `vn.acme.platform:order-service:2.0.0` nếu không có cấu hình khác thay đổi version.

Kế thừa giúp nhiều module dùng chung namespace và phiên bản mà không cần lặp lại cùng giá trị trong từng POM. Khi đọc một POM con, nếu không thấy `groupId` hoặc `version`, hãy kiểm tra phần `<parent>` trước khi kết luận tọa độ bị thiếu.

## 3. `artifactId`: tên artifact trong một group

`artifactId` là tên của artifact cụ thể trong namespace được xác định bởi `groupId`. Nó thường ngắn gọn, mô tả vai trò hoặc chức năng của thư viện/ứng dụng:

```text
order-service
payment-api
platform-security
logging-starter
customer-domain
```

Khi kết hợp với `groupId`, `artifactId` phân biệt các sản phẩm trong cùng một namespace:

```text
vn.acme.platform:platform-security:2.0.0
vn.acme.platform:logging-starter:2.0.0
vn.acme.order:order-service:2.0.0
```

Ba artifact trên có thể cùng được phát hành bởi một tổ chức nhưng đảm nhiệm các vai trò khác nhau.

### 3.1. Đặt artifactId theo vai trò

Nên chọn tên phản ánh nội dung mà artifact cung cấp. Ví dụ:

| Tên | Cách hiểu |
|---|---|
| `customer-api` | API hoặc hợp đồng dùng chung cho miền khách hàng |
| `customer-domain` | Mô hình và quy tắc nghiệp vụ miền khách hàng |
| `customer-service` | Ứng dụng/service triển khai chức năng khách hàng |
| `customer-test-fixtures` | Dữ liệu và tiện ích dùng trong kiểm thử |
| `platform-observability` | Thành phần quan sát hệ thống dùng chung |

Một dự án nhiều module thường dùng cùng `groupId` nhưng có `artifactId` riêng cho từng module. Cách đặt tên nên nhất quán để người sử dụng hiểu được vai trò của dependency ngay khi đọc POM.

### 3.2. `artifactId` không phải tên file Java hoặc package

`artifactId` không nhất thiết trùng tên thư mục mã nguồn, tên class chính hoặc package Java. Ví dụ artifact `vn.acme.order:order-service:1.0.0` có thể chứa lớp `vn.acme.orders.Application`, nhiều package khác và các resource. Tên JAR mặc định thường được tạo từ `artifactId` và `version`, nhưng cấu hình build có thể thay đổi tên file đầu ra.

## 4. `version`: phiên bản của artifact

`version` xác định bản phát hành hoặc bản phát triển của artifact. Ví dụ:

```text
1.0.0
1.2.0
2.0.0
2.0.0-SNAPSHOT
2.1.0-RC1
```

Maven không bắt buộc mọi dự án phải tuân theo Semantic Versioning, nhưng nhiều nhóm dùng quy ước `MAJOR.MINOR.PATCH` vì dễ truyền đạt mức độ thay đổi:

- **MAJOR**: thay đổi có thể phá vỡ tương thích API hoặc hành vi.
- **MINOR**: bổ sung chức năng tương thích ngược.
- **PATCH**: sửa lỗi tương thích ngược.

Đây là quy ước quản lý phiên bản của nhóm. Maven nhận giá trị version như một phần định danh và có thuật toán so sánh phiên bản riêng; nó không tự xác minh rằng nhóm đã tăng đúng MAJOR, MINOR hay PATCH theo SemVer.

### 4.1. Release version

Một release version thường đại diện cho bản phát hành ổn định, ví dụ:

```text
1.0.0
1.3.2
2.0.0
```

Theo quy ước repository tốt, một tọa độ release đã phát hành nên bất biến: không ghi đè nội dung artifact của `1.3.2` bằng một binary khác. Nếu cần phát hành bản sửa lỗi, tạo version mới, chẳng hạn `1.3.3`.

Tính bất biến giúp build có thể tái tạo. Khi một POM yêu cầu `vn.acme:customer-api:1.3.2`, người build có thể tin rằng repository trả về đúng nội dung đã được phát hành cho version đó.

### 4.2. Snapshot version

Hậu tố `-SNAPSHOT` biểu thị một bản phát triển chưa phải release cố định:

```text
1.4.0-SNAPSHOT
```

Trong quá trình phát triển, nhóm có thể publish nhiều lần artifact cùng tọa độ logic `1.4.0-SNAPSHOT`. Maven repository quản lý snapshot metadata để xác định bản snapshot cụ thể mới nhất, thường lưu artifact thực tế với timestamp và build number.

Ví dụ tên file lưu trong snapshot repository có thể giống:

```text
order-service-1.4.0-20261113.061500-3.jar
```

Tên timestamp này là ví dụ minh họa. Dependency vẫn tham chiếu version logic `1.4.0-SNAPSHOT`; Maven sử dụng metadata repository để tìm snapshot phù hợp.

Snapshot phù hợp cho tích hợp trong quá trình phát triển, nhưng làm giảm tính tái lập nếu build không kiểm soát thời điểm cập nhật. Hai lần build cùng POM có thể nhận nội dung snapshot khác nhau nếu repository đã được publish snapshot mới và chính sách cập nhật cho phép lấy bản mới.

### 4.3. Pre-release version

Một số dự án dùng hậu tố để chỉ trạng thái trước release:

```text
2.0.0-alpha1
2.0.0-beta2
2.0.0-M1
2.0.0-RC1
```

Các hậu tố như `alpha`, `beta`, `M` (milestone) và `RC` (release candidate) là quy ước đặt tên phổ biến. Maven có thuật toán so sánh version để sắp xếp nhiều dạng version, nhưng không áp đặt quy trình phát hành cụ thể cho nhóm.

Không nên tự giả định thứ tự chỉ bằng cách so sánh chuỗi ký tự. Ví dụ `1.10.0` phải được hiểu theo các thành phần version, không phải nhỏ hơn `1.9.0` vì ký tự đầu tiên sau dấu chấm là `1`.

### 4.4. Version range và phiên bản động

Maven hỗ trợ version range trong một số khai báo dependency, ví dụ:

```xml
<version>[1.2,2.0)</version>
```

Khoảng này biểu thị phiên bản từ `1.2` trở lên nhưng nhỏ hơn `2.0` theo cách Maven xử lý version. Tuy nhiên, version range hoặc các lựa chọn động có thể khiến kết quả phân giải thay đổi theo trạng thái repository. Để build có tính tái lập cao, nhiều dự án ưu tiên khai báo version cụ thể hoặc quản lý phiên bản tập trung bằng BOM/`dependencyManagement`.

Không nên dùng `LATEST` hoặc `RELEASE` như một cách quản lý dependency lâu dài. Các lựa chọn này làm cho phiên bản được chọn phụ thuộc repository và cơ chế cập nhật, gây khó khăn khi tái tạo kết quả build.

## 5. GAV được dùng ở đâu trong POM?

GAV xuất hiện ở nhiều vị trí khác nhau trong POM. Cần phân biệt tọa độ của chính project với tọa độ của dependency và tọa độ của parent.

### 5.1. Tọa độ của project hiện tại

Phần đầu POM mô tả artifact mà project sẽ tạo:

```xml
<groupId>vn.acme.order</groupId>
<artifactId>order-service</artifactId>
<version>1.4.0</version>
```

Đây là tọa độ của project. Khi chạy `mvn install`, Maven cài artifact vào local repository với định danh này. Khi deploy, Maven publish artifact và POM tương ứng lên remote repository đã cấu hình.

### 5.2. Tọa độ của parent POM

Phần `<parent>` xác định POM mà project kế thừa:

```xml
<parent>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>2.0.0</version>
</parent>
```

Parent có GAV riêng. GAV này không phải GAV của module con. Parent cung cấp cấu hình có thể kế thừa như properties, dependency management, plugin management và một số thiết lập build.

### 5.3. Tọa độ của dependency

Một dependency thông thường khai báo GAV của artifact cần sử dụng:

```xml
<dependencies>
    <dependency>
        <groupId>vn.acme.platform</groupId>
        <artifactId>platform-security</artifactId>
        <version>2.0.0</version>
    </dependency>
</dependencies>
```

Maven dùng tọa độ này để tìm POM và artifact trong repository, sau đó phân giải các dependency bắc cầu theo metadata của dependency.

Dependency còn có thể khai báo `scope`, `type`, `classifier`, `optional` hoặc `exclusions`. Những thuộc tính này điều chỉnh cách dependency được sử dụng và phân giải; chúng không thay thế ba thành phần GAV.

### 5.4. Bỏ version khi đã được quản lý

Nếu version đã được khai báo trong `dependencyManagement`, module có thể bỏ `<version>` tại dependency sử dụng:

```xml
<!-- Parent POM -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.acme.platform</groupId>
            <artifactId>platform-security</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con:

```xml
<dependencies>
    <dependency>
        <groupId>vn.acme.platform</groupId>
        <artifactId>platform-security</artifactId>
    </dependency>
</dependencies>
```

Dependency vẫn có tọa độ hiệu lực đầy đủ vì Maven lấy version từ dependency management. `dependencyManagement` quản lý version và một số thuộc tính mặc định; nó không tự thêm dependency vào classpath của mọi module. Module vẫn cần khai báo dependency trong `<dependencies>` nếu muốn sử dụng nó.

## 6. Tọa độ Maven và cấu trúc repository

GAV không chỉ xuất hiện trong POM. Maven dùng tọa độ để xác định đường dẫn lưu artifact trong repository.

Với một release artifact:

```text
groupId:    vn.acme.platform
artifactId: platform-security
version:    2.0.0
```

Đường dẫn repository thường có dạng:

```text
vn/acme/platform/platform-security/2.0.0/
    platform-security-2.0.0.pom
    platform-security-2.0.0.jar
```

Quy tắc tổng quát:

```text
<repository-root>/
  <groupId chuyển dấu chấm thành dấu gạch chéo>/
    <artifactId>/
      <version>/
        <artifactId>-<version>.<extension>
```

Nếu artifact có classifier, classifier được thêm vào tên file:

```text
platform-security-2.0.0-sources.jar
platform-security-2.0.0-javadoc.jar
```

Trong ví dụ này, `sources` và `javadoc` là classifier. Chúng phân biệt các artifact phụ được phát hành cùng GAV chính.

Repository cũng lưu metadata, đặc biệt cho snapshot version và thông tin phiên bản. Vì vậy, không nên tự tạo đường dẫn repository rồi đoán tên file trong mọi trường hợp; hãy để Maven resolver sử dụng tọa độ và metadata của repository.

## 7. Mở rộng tọa độ: type, extension và classifier

GAV là định danh cơ bản. Trong Maven dependency model, artifact còn có thể được phân biệt bằng `type` và `classifier`.

Ví dụ dependency JAR thông thường:

```xml
<dependency>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-security</artifactId>
    <version>2.0.0</version>
</dependency>
```

Ví dụ yêu cầu artifact chứa source code:

```xml
<dependency>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-security</artifactId>
    <version>2.0.0</version>
    <classifier>sources</classifier>
</dependency>
```

Ví dụ yêu cầu artifact có type `test-jar` và classifier `tests`:

```xml
<dependency>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-security</artifactId>
    <version>2.0.0</version>
    <type>test-jar</type>
    <classifier>tests</classifier>
</dependency>
```

`type` là cách Maven xác định loại artifact thông qua artifact handler; nó thường liên quan đến extension và classifier mặc định. `classifier` phân biệt biến thể của cùng một artifact, chẳng hạn `sources`, `javadoc`, `tests` hoặc một biến thể được nhóm tự định nghĩa.

Vì vậy, khi nói về GAV, ta đang nói đến ba thành phần cốt lõi. Khi cần phân biệt chính xác một dependency variant, cần xem thêm type/classifier và các thuộc tính liên quan.

## 8. Tọa độ trong dự án Maven nhiều module

Một Maven reactor build thường có nhiều module. Mỗi module có thể tạo artifact riêng với `artifactId` riêng. Các module thường dùng chung `groupId` và version thông qua parent POM.

Ví dụ root POM:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.acme.order</groupId>
    <artifactId>order-platform</artifactId>
    <version>1.4.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>order-api</module>
        <module>order-domain</module>
        <module>order-service</module>
    </modules>
</project>
```

Module con có thể kế thừa tọa độ cha và chỉ khai báo artifactId riêng:

```xml
<!-- order-domain/pom.xml -->
<project>
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.acme.order</groupId>
        <artifactId>order-platform</artifactId>
        <version>1.4.0</version>
    </parent>

    <artifactId>order-domain</artifactId>
</project>
```

Khi đó tọa độ module là:

```text
vn.acme.order:order-domain:1.4.0
```

Các module khác có thể có tọa độ:

```text
vn.acme.order:order-api:1.4.0
vn.acme.order:order-service:1.4.0
```

Root aggregator có `packaging` là `pom` để gom các module trong reactor. Một POM vừa có thể là aggregator, vừa có thể là parent để module con kế thừa, nhưng hai vai trò này khác nhau về mặt khái niệm.

### 8.1. Dependency giữa các module

Nếu `order-service` sử dụng `order-domain`, dependency được khai báo bằng tọa độ Maven:

```xml
<dependency>
    <groupId>vn.acme.order</groupId>
    <artifactId>order-domain</artifactId>
    <version>${project.version}</version>
</dependency>
```

Trong cùng reactor build, Maven có thể nhận diện module cung cấp dependency và sắp xếp thứ tự build theo quan hệ phụ thuộc. Nếu build module riêng bên ngoài reactor, artifact cần có sẵn trong local hoặc remote repository.

`<modules>` trong root POM xác định những project tham gia reactor; nó không tự động làm mọi module phụ thuộc vào nhau. Quan hệ dependency phải được khai báo riêng trong module tiêu thụ.

## 9. `groupId`, `artifactId`, `version` và các trường POM dễ nhầm

POM có nhiều trường tên gần giống nhau. Một số trường không phải thành phần GAV:

| Trường | Ý nghĩa | Có thuộc GAV? |
|---|---|---|
| `groupId` | Namespace/nhóm của artifact | Có |
| `artifactId` | Tên artifact trong nhóm | Có |
| `version` | Phiên bản artifact | Có |
| `modelVersion` | Phiên bản mô hình POM mà tệp tuân theo | Không |
| `packaging` | Kiểu artifact project tạo ra, ví dụ `jar`, `war`, `pom` | Không |
| `name` | Tên hiển thị thân thiện của project | Không |
| `description` | Mô tả project | Không |
| `url` | Trang thông tin của project | Không |

Đặc biệt, `<modelVersion>4.0.0</modelVersion>` không có nghĩa artifact đang ở version `4.0.0`. Nó chỉ cho biết POM sử dụng mô hình POM version 4.0.0. Version artifact được khai báo bằng `<version>` ở cấp project hoặc kế thừa từ parent.

`packaging` cũng không thuộc GAV. Nó cho biết loại sản phẩm mà project đóng gói. Nếu không khai báo packaging trong một project Maven thông thường, mặc định thường là `jar`; một parent/aggregator POM thường dùng `pom`.

## 10. Tọa độ và dependency conflict

Một project có thể phụ thuộc trực tiếp vào nhiều artifact, trong khi các artifact đó lại có dependency bắc cầu. Khi cùng một `groupId:artifactId` xuất hiện với nhiều version, Maven cần chọn version phù hợp theo dependency mediation.

Ví dụ:

```text
application
├── library-a
│   └── vn.acme:common-utils:1.2.0
└── library-b
    └── vn.acme:common-utils:1.5.0
```

Maven thường dùng quy tắc nearest definition: dependency có đường dẫn gần project nhất được ưu tiên. Nếu hai phiên bản ở cùng độ sâu, thứ tự khai báo trong POM có thể quyết định phiên bản được chọn. Đây là một lý do cần kiểm tra dependency tree thay vì chỉ đọc dependency trực tiếp.

Có thể xem dependency tree bằng:

```bash
./mvnw dependency:tree
```

Để tìm lý do một artifact/version được chọn, có thể dùng:

```bash
./mvnw dependency:tree -Dincludes=vn.acme:common-utils
```

Hoặc dùng `dependency:tree` với các tùy chọn lọc phù hợp của plugin. Khi cần loại bỏ dependency bắc cầu không mong muốn, Maven hỗ trợ `<exclusions>` trong dependency declaration. Khi cần đồng bộ version của một nhóm dependency, `dependencyManagement` hoặc BOM là cách quản lý phổ biến.

### 10.1. BOM và tọa độ POM

Bill of Materials (BOM) là một POM dùng để quản lý version của một nhóm dependency. BOM thường được import trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Ở đây BOM cũng được xác định bằng GAV, nhưng `type=pom` và `scope=import` chỉ ra rằng POM được dùng để nhập các quy tắc dependency management. Việc import BOM không tự thêm tất cả dependency của BOM vào project.

## 11. Tọa độ Maven trong lệnh và công cụ

Một số công cụ nhận tọa độ Maven ở dạng chuỗi:

```text
groupId:artifactId:version
```

Ví dụ:

```text
org.apache.commons:commons-lang3:3.17.0
```

Tọa độ này có thể xuất hiện trong:

- Dependency declaration trong POM.
- Dependency report và dependency tree.
- Lệnh plugin hoặc tham số tìm kiếm artifact.
- Metadata repository và đường dẫn artifact.
- Log phân giải dependency.
- Cấu hình version catalog hoặc hệ thống quản lý dependency khác.

Khi đọc log Maven, hãy đối chiếu đủ cả ba thành phần. Nếu thấy `Could not find artifact`, hãy kiểm tra groupId, artifactId, version, repository được sử dụng, classifier/type nếu có và chính sách snapshot/release của repository.

## 12. Quy ước version để build có thể tái tạo

Tọa độ Maven chỉ hữu ích khi nhóm quản lý nó nhất quán.

### 12.1. Không tái sử dụng release version cho nội dung khác

Nếu `vn.acme:order-api:1.4.0` đã được phát hành, không nên upload binary khác dưới cùng tọa độ. Người dùng có thể đã cache artifact cũ, trong khi người khác tải artifact mới; hai môi trường khi đó cùng khai báo một GAV nhưng nhận nội dung khác nhau.

Hãy tạo version mới khi nội dung phát hành thay đổi. Quy tắc này giúp dependency cache và repository hoạt động ổn định.

### 12.2. Dùng SNAPSHOT có chủ đích

Snapshot hữu ích khi nhiều module cần thử nghiệm thay đổi chưa phát hành. Tuy nhiên, vì snapshot có thể thay đổi, cần cân nhắc chính sách cập nhật và cache. Với build release, nên dùng các dependency release cố định để kết quả có thể tái tạo.

### 12.3. Quản lý version tập trung

Trong dự án nhiều module, có thể đặt version chung trong parent POM:

```xml
<properties>
    <platform.version>2.0.0</platform.version>
</properties>
```

Sau đó dùng property trong dependency management:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.acme.platform</groupId>
            <artifactId>platform-security</artifactId>
            <version>${platform.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Cách này giúp thay đổi version ở một vị trí. Với các hệ sinh thái hoặc dự án dùng BOM, BOM có thể đóng vai trò nguồn quản lý version chung. Dù chọn cách nào, cần xác định rõ nơi sở hữu version để tránh nhiều module tự khai báo các giá trị không đồng bộ.

## 13. Cách đọc một dependency declaration

Hãy xem ví dụ:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
    <scope>compile</scope>
</dependency>
```

Có thể diễn giải từng phần:

1. Maven tìm artifact thuộc namespace `org.apache.commons`.
2. Artifact cần dùng có tên `commons-lang3`.
3. Phiên bản được yêu cầu là `3.17.0`.
4. Scope `compile` xác định phạm vi dependency trong các classpath/lifecycle liên quan.
5. Maven tìm POM/artifact trong local repository hoặc remote repository đã cấu hình.
6. Nếu POM của dependency có dependency bắc cầu, Maven tiếp tục phân giải theo quy tắc mediation và scope.

`scope` không thuộc GAV. Nó quyết định dependency được dùng ở đâu trong vòng đời build. Các scope phổ biến gồm `compile`, `provided`, `runtime`, `test`, `system` và `import` (scope import dùng trong dependency management cho BOM).

## 14. Những lỗi thường gặp liên quan đến GAV

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `Could not find artifact ...` | Sai groupId/artifactId/version hoặc artifact chưa được publish vào repository đang dùng | Đối chiếu tọa độ, repository URL, snapshot/release policy và classifier/type |
| Dependency không tìm thấy dù đã build module | Module chưa được cài vào local repository hoặc không nằm trong cùng reactor build | Chạy build ở root reactor hoặc `mvn install` theo quy trình phù hợp |
| Module con thiếu groupId/version | Chưa khai báo trực tiếp và cũng không kế thừa từ parent như dự kiến | Kiểm tra `<parent>` và effective POM |
| Dùng nhầm version | Parent, profile hoặc `dependencyManagement` cung cấp giá trị khác | Xem `help:effective-pom` và dependency tree |
| Máy local có dependency nhưng CI không có | Artifact chỉ được cài vào local repository trên máy cá nhân | Publish artifact lên repository dùng chung hoặc build các module trong cùng reactor |
| Hai máy nhận binary khác nhau với cùng release GAV | Repository cho phép ghi đè release hoặc cache không đồng nhất | Kiểm tra chính sách repository và tính bất biến của release |
| Không tìm thấy JAR có classifier | Classifier chưa được publish hoặc tên classifier/type khai báo sai | Kiểm tra danh sách artifact thực tế trong repository |

Một tọa độ đúng cú pháp không bảo đảm artifact đã tồn tại. GAV chỉ định danh thứ cần tìm; repository phải thực sự chứa artifact tương ứng và người build phải có quyền truy cập.

## 15. Những điều cần ghi nhớ

- GAV là viết tắt của `groupId`, `artifactId` và `version`.
- `groupId` xác định namespace/nhóm sở hữu; `artifactId` xác định artifact trong nhóm; `version` xác định bản phát hành.
- `groupId` và `version` của module con có thể được kế thừa từ parent POM; `artifactId` xác định tên riêng của module.
- GAV xuất hiện trong tọa độ project, parent và dependency; cần phân biệt từng ngữ cảnh.
- Maven dùng GAV để tìm artifact trong repository và tổ chức đường dẫn theo groupId, artifactId, version.
- `SNAPSHOT` là version phát triển có thể cập nhật; release version nên bất biến.
- `type` và `classifier` phân biệt biến thể artifact; `scope` điều chỉnh phạm vi sử dụng dependency và không phải thành phần GAV.
- `modelVersion` trong POM không phải version của artifact.
- `dependencyManagement` quản lý version mặc định nhưng không tự thêm dependency vào project.
- Dependency tree và effective POM giúp xác định version thực tế được Maven chọn.

Khi gặp một dependency Maven, hãy đọc đủ `groupId`, `artifactId` và `version` trước khi tìm kiếm hoặc thay đổi nó. Khi phát hành artifact, hãy chọn namespace ổn định, tên có ý nghĩa và version phản ánh đúng trạng thái sản phẩm. Ba thành phần này là nền tảng để Maven phân biệt, chia sẻ và tái sử dụng các thành phần Java giữa những dự án khác nhau.
