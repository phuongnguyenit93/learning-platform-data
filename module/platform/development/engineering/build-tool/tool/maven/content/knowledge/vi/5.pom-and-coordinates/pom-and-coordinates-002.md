# project, namespace, schema và modelVersion trong Maven POM

`pom.xml` là tệp XML mô tả một dự án Maven: danh tính artifact, kiểu đóng gói, quan hệ cha–con, dependency, plugin và các cấu hình build. Ở đầu phần lớn POM, ta thấy một cụm khai báo khá dài:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>my-app</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</project>
```

Bốn khái niệm trọng tâm cần phân biệt:

| Khái niệm | Trong ví dụ | Vai trò |
| --- | --- | --- |
| **`project`** | Thẻ `<project>...</project>` | Phần tử gốc bao toàn bộ cấu hình của một Maven project |
| **XML namespace** | `xmlns="http://maven.apache.org/POM/4.0.0"` | Không gian tên để xác định chính xác các phần tử XML thuộc mô hình POM nào |
| **XML Schema (XSD)** | `xsi:schemaLocation="... https://maven.apache.org/xsd/maven-4.0.0.xsd"` | Gợi ý cho công cụ XML biết tệp schema kiểm tra cấu trúc phần tử/thuộc tính |
| **`modelVersion`** | `<modelVersion>4.0.0</modelVersion>` | Phiên bản **mô hình POM** mà Maven cần đọc và diễn giải |

Bốn thành phần có quan hệ nhưng **không đồng nghĩa**. Đặc biệt, `modelVersion` không phải phiên bản của Maven đang cài, không phải phiên bản sản phẩm được build và không phải phiên bản của plugin.

## 1. `<project>`: phần tử gốc của một POM

Một tài liệu XML hợp lệ có **một phần tử gốc duy nhất**. Với POM Maven, phần tử đó là `<project>`; các cấu hình Maven được đặt bên trong nó.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
</project>
```

Đây là một **POM độc lập tối thiểu** cho dự án Maven 3 theo model 4.0.0. Trong ví dụ:

- `groupId` định danh nhóm/tổ chức, chẳng hạn `vn.example`.
- `artifactId` định danh artifact trong nhóm, chẳng hạn `hello-maven`.
- `version` là phiên bản artifact được phát hành hoặc build.
- `modelVersion` nói Maven cần dùng mô hình dữ liệu POM nào.

Tọa độ artifact là `vn.example:hello-maven:1.0.0`. Dù `groupId` trông giống tên miền Java và mặc dù namespace cũng chứa URL, **`groupId` không phải XML namespace**. Khi POM có `<parent>`, `groupId` hoặc `version` của project con có thể được kế thừa thay vì khai báo trực tiếp; `artifactId` vẫn phải định nghĩa cho project.

`<project>` khác phần tử `<projects>` hay `<dependency>`: không thể thay thẻ gốc bằng tên khác và mong Maven tự hiểu. Nội dung như `<dependencies>`, `<build>` hoặc `<profiles>` đều phải nằm ở vị trí hợp lệ bên trong `<project>`.

Cụm `<?xml version="1.0" encoding="UTF-8"?>` đầu file là **XML declaration**, hoàn toàn khác `<project><version>` và `modelVersion`. Nó chỉ cho biết phiên bản cú pháp XML và encoding của tài liệu; với XML UTF-8, khai báo này thường được giữ lại vì rõ ràng, dù không phải lúc nào cũng bắt buộc.

## 2. XML namespace: `xmlns` dùng để làm gì?

### 2.1. Không gian tên định danh các phần tử, không phải địa chỉ tải dependency

Dòng:

```xml
xmlns="http://maven.apache.org/POM/4.0.0"
```

khai báo **default XML namespace** trên phần tử `project` và các phần tử con không có tiền tố. Vì vậy, `<project>`, `<modelVersion>`, `<groupId>` và `<dependencies>` đều được hiểu là các tên phần tử thuộc namespace:

```text
http://maven.apache.org/POM/4.0.0
```

XML phân biệt phần tử bằng cặp **(namespace URI, local name)**. Ví dụ `<modelVersion>` được nhận diện theo local name `modelVersion` trong namespace POM, không chỉ theo chuỗi chữ `modelVersion`.

Namespace URI là **định danh**, không mặc nhiên là URL mà Maven phải tải qua mạng khi build. Nó cũng **không phải** Maven Central, repository URL, website ứng dụng hay `groupId` của artifact. Dùng `http://maven.apache.org/POM/4.0.0` đúng như namespace được Maven công bố; không tự thay thành `https://maven.apache.org/POM/4.0.0` chỉ vì XSD bên dưới có URL HTTPS: hai chuỗi URI khác nhau.

### 2.2. `xmlns:xsi` giới thiệu tiền tố `xsi`

Dòng:

```xml
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
```

khai báo tiền tố `xsi` dùng cho các thuộc tính thuộc **XML Schema Instance**. Nhờ vậy cú pháp `xsi:schemaLocation` có ý nghĩa. Nó không tạo một project khác, không khai báo plugin và không yêu cầu mã Java dùng package `xsi`.

Hai namespace có vai trò riêng:

- Namespace mặc định `xmlns="http://maven.apache.org/POM/4.0.0"` áp dụng cho tên phần tử POM không tiền tố.
- Namespace `xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"` gắn với tiền tố của thuộc tính `xsi:schemaLocation`.

Nếu viết `xsi:schemaLocation` mà không khai báo `xmlns:xsi`, XML parser theo namespace sẽ gặp **tiền tố chưa được ràng buộc** (unbound prefix). Nếu thừa/thiếu dấu ngoặc kép khi khai báo `xmlns` thì XML có thể không còn well-formed.

### 2.3. Có cần dùng tiền tố `pom:` không?

Về nguyên tắc XML namespace, có thể dùng tiền tố rõ ràng như:

```xml
<pom:project xmlns:pom="http://maven.apache.org/POM/4.0.0">
    <pom:modelVersion>4.0.0</pom:modelVersion>
    <pom:groupId>vn.example</pom:groupId>
    <pom:artifactId>hello-maven</pom:artifactId>
    <pom:version>1.0.0</pom:version>
</pom:project>
```

Ví dụ này **minh họa cơ chế XML namespace**, không phải mẫu POM khuyến nghị cho Maven. Khi dùng Maven trong thực tế, ưu tiên cú pháp chuẩn **default namespace** không tiền tố theo tài liệu chính thức; khả năng đọc các kiểu prefix tùy thuộc parser/tooling và không nên giả định mọi tiện ích Maven đều xử lý như một XML validator thuần.

## 3. Schema (XSD): `xsi:schemaLocation` liên hệ namespace với quy tắc cấu trúc

Đối với POM model 4.0.0, khai báo phổ biến là:

```xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                    https://maven.apache.org/xsd/maven-4.0.0.xsd"
```

Đây là **một giá trị thuộc tính** gồm các phần ngăn cách bằng khoảng trắng (xuống dòng chỉ giúp đọc dễ hơn). Một cặp trong `schemaLocation` có cấu trúc:

```text
<namespace-URI> <URL-hoặc-vị-trí-XSD>
```

Cụ thể:

1. `http://maven.apache.org/POM/4.0.0` là namespace **mà schema mô tả**.
2. `https://maven.apache.org/xsd/maven-4.0.0.xsd` là vị trí tài liệu **XSD** tương ứng.

**Thứ tự có ý nghĩa.** Trường đầu không phải link tới file; trường thứ hai mới là địa chỉ tài nguyên schema. Khi khai báo nhiều namespace có thể có nhiều cặp, nhưng POM thông thường chỉ cần một cặp cho namespace Maven.

XSD có thể mô tả những phần tử và thuộc tính nào hợp lệ, kiểu dữ liệu, quan hệ lồng nhau và một số ràng buộc cấu trúc. IDE/XML editor có thể dùng XSD cho autocomplete, gợi ý thuộc tính hoặc phát hiện cấu trúc sai. `schemaLocation` là **gợi ý cho công cụ có chức năng schema validation**, không phải cam kết rằng Maven sẽ truy cập URL XSD mỗi lần build.

**Phân biệt ba mức kiểm tra:**

- **XML well-formed:** mở/đóng tag khớp, chỉ có một root, dấu quote hợp lệ, escape ký tự đặc biệt; XML parser cơ bản kiểm tra được.
- **XSD-valid:** document phù hợp cấu trúc và kiểu mà XSD mô tả; chỉ được bảo đảm nếu một XML validator thực sự thực hiện schema validation.
- **Maven-valid/buildable:** Maven diễn giải được POM, giải quyết parent, dependency/plugin và các quy tắc model/build; còn có điều kiện vượt phạm vi XSD, như tọa độ, repository, version và lifecycle.

Vì vậy, **có khai báo XSD không đồng nghĩa build sẽ thành công**, và thiếu khai báo `xsi:schemaLocation` không nhất thiết làm Maven từ chối một POM hợp lệ về mô hình. Maven đọc mô hình POM bằng công cụ riêng; đừng suy luận rằng URL XSD là dependency được tải từ Maven Central. Nếu IDE hiện “Cannot resolve schema”, có thể là sự cố mạng/cấu hình XML editor trong khi Maven vẫn xây dựng mô hình được.

## 4. `<modelVersion>`: phiên bản mô hình POM, không phải Maven executable

Phần tử:

```xml
<modelVersion>4.0.0</modelVersion>
```

xác định phiên bản **POM model**. Với POM Maven 3 thông dụng, giá trị là `4.0.0`. Giá trị này không đồng nghĩa:

- `mvn --version`: phiên bản chương trình Maven được cài hoặc Wrapper đang chạy (ví dụ Maven 3.9.x).
- `<project><version>1.0.0</version>`: phiên bản artifact ứng dụng.
- `<plugin><version>...`: phiên bản một Maven plugin.
- `<?xml version="1.0"?>`: phiên bản chuẩn XML.

**Ví dụ:** terminal chạy Maven 3.9.x, POM ghi `<modelVersion>4.0.0</modelVersion>` và `<version>2.3.0-SNAPSHOT</version>`. Đó là ba con số khác nhau: phiên bản Maven runtime, mô hình POM, phiên bản artifact. Không cần đặt chúng bằng nhau.

### 4.1. Maven 4 và POM model 4.1.0

Tài liệu Maven 4 giới thiệu POM model **`4.1.0`** cùng namespace và XSD tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven4-example</artifactId>
    <version>1.0.0</version>
</project>
```

Đây là ví dụ **build POM dành cho công cụ Maven 4 hỗ trợ model 4.1.0**. Không sử dụng nó với Maven 3. Maven 4 vẫn hỗ trợ build các POM `4.0.0`; **không cần nâng modelVersion chỉ vì đổi Maven runtime sang Maven 4**.

Model 4.1.0 hỗ trợ một số cấu trúc và tính năng mới của Maven 4. Để không phá tương thích khi publish, Maven 4 có cơ chế tạo **consumer POM** theo mô hình `4.0.0` từ build POM `4.1.0` khi phát hành artifact, theo khả năng chuyển đổi. Vì vậy có thể gặp build POM `4.1.0` trong source nhưng POM được người dùng tải từ repository vẫn là `4.0.0`.

Các giá trị liên quan cần được xem là **một bộ nhất quán**:

| Ngữ cảnh | `xmlns` | `xsi:schemaLocation` (namespace, file XSD) | `modelVersion` |
| --- | --- | --- | --- |
| POM 4.0.0 cho Maven 3 và Maven 4 | `http://maven.apache.org/POM/4.0.0` | `http://maven.apache.org/POM/4.0.0`, `https://maven.apache.org/xsd/maven-4.0.0.xsd` | `4.0.0` |
| Build POM Maven 4 dùng mô hình mới | `http://maven.apache.org/POM/4.1.0` | `http://maven.apache.org/POM/4.1.0`, `https://maven.apache.org/xsd/maven-4.1.0.xsd` | `4.1.0` |

**Không sửa riêng một trong ba giá trị rồi cho rằng đã migrate thành công.** Sự tương thích thực tế do Maven runtime và mô hình POM mà runtime hỗ trợ quyết định.

## 5. Ví dụ hoàn chỉnh: phân tích từng dòng đầu POM 4.0.0

Một POM thực hành (tên file là `pom.xml`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.training</groupId>
    <artifactId>pom-basics</artifactId>
    <version>1.2.0-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>POM Basics</name>
    <description>Ví dụ cấu trúc gốc của Maven POM</description>
</project>
```

Đây là POM độc lập hợp lệ về cấu trúc, dùng packaging `jar` mặc định nhưng khai báo tường minh để dễ học. Nó không yêu cầu có mã Java chỉ để kiểm tra POM; còn việc `package` tạo file JAR có nội dung thực tế phụ thuộc source và plugin chạy trong build.

**Giải thích theo thứ tự:**

1. `<?xml ... ?>`: khai báo XML 1.0, UTF-8.
2. `<project ...>`: mở root descriptor.
3. `xmlns=.../POM/4.0.0`: đặt default namespace của các phần tử POM.
4. `xmlns:xsi=...`: khai báo tiền tố `xsi` cho thuộc tính schema-related.
5. `xsi:schemaLocation=...`: nối namespace POM với đường dẫn XSD; giúp editor/validator.
6. `<modelVersion>4.0.0</modelVersion>`: chỉ định phiên bản mô hình POM.
7. `<groupId>`, `<artifactId>`, `<version>`: tọa độ artifact độc lập với phiên bản model.
8. `<packaging>jar</packaging>`: kiểu artifact; `jar` là mặc định trong nhiều POM dự án.
9. `<name>` và `<description>`: metadata hiển thị, không ảnh hưởng danh tính artifact.
10. `</project>`: đóng root; sau đó không thể thêm một root XML thứ hai.

**Lệnh tự kiểm tra** tại thư mục chứa `pom.xml` và có Maven/Wrapper:

```bash
mvn --version
mvn -f pom.xml validate
mvn help:effective-pom -Doutput=effective-pom.xml
```

- Lệnh đầu hiện **Maven runtime và Java**, không cho biết `modelVersion`.
- `validate` yêu cầu Maven đọc POM; thành công chứng minh cấu trúc và ràng buộc mà Maven kiểm tra ở bước này hợp lệ. Với POM trên, có thể chạy `validate` ngay cả khi chưa có thư mục `src`. Nếu dùng Wrapper, thay `mvn` bằng `./mvnw` (Unix) hoặc `.\mvnw.cmd` (PowerShell).
- `help:effective-pom` (cần Help Plugin và khả năng tải plugin nếu cache chưa có) tạo `effective-pom.xml` để thấy POM sau inheritance và mặc định; không sửa bản gốc. Đây là dữ liệu Maven tính được, không phải bản sao nguyên văn XML đầu vào.

Trên môi trường có lệnh `xmllint`, kiểm tra cú pháp XML riêng:

```bash
xmllint --noout pom.xml
```

Nếu lệnh trả về exit code `0`, XML **well-formed**; chưa chứng minh POM hợp lệ với Maven. Khi muốn chạy XSD validation, phải sử dụng trình kiểm tra XSD phù hợp và schema đáng tin cậy, đồng thời hiểu rằng một POM đi qua XSD chưa chắc build thành công.

## 6. Một POM rút gọn có cần khai báo namespace và schema đầy đủ không?

Trong thực tế bạn có thể gặp POM ngắn hơn:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>simple</artifactId>
    <version>1.0.0</version>
</project>
```

Maven có khả năng đọc dạng POM tối giản như trên trong môi trường phù hợp; ví dụ này **không có XML namespace mặc định và không gắn schemaLocation**, nên IDE/XML validator có thể không cung cấp cùng mức kiểm tra hoặc gợi ý XSD.

Khi xây dựng POM để chia sẻ, nên dùng cấu trúc root theo tài liệu Maven với `xmlns`, `xmlns:xsi` và `xsi:schemaLocation` để người đọc cùng công cụ nhận diện rõ model. Tuy nhiên, đừng khẳng định thiếu `schemaLocation` chính là nguyên nhân của mọi lỗi Maven: phải kiểm tra thông báo lỗi thực tế.

### Namespace trong POM khác namespace trong những file XML khác

`pom.xml` của Maven có namespace `.../POM/4.0.0`; còn `settings.xml` là loại tài liệu khác, có namespace `.../SETTINGS/...` và XSD riêng. **Không copy namespace/settings schema vào POM** hoặc dùng XSD của plugin configuration cho root POM.

Tương tự, namespace khai báo trong tệp Java XML (ví dụ Spring XML) thuộc format khác, không thay thế POM model. Các tên như `groupId`, package Java hoặc `artifactId` không tự tạo/đổi namespace XML.

## 7. Lỗi phổ biến và cách tìm nguyên nhân

| Sai sót | Dấu hiệu/hậu quả | Cách khắc phục |
| --- | --- | --- |
| Root bị đổi thành `<pom>` hoặc `<dependencies>` | Maven không nhận ra descriptor root | Dùng `<project>` với cấu trúc POM hợp lệ |
| Gõ `<modelversion>` thay vì `<modelVersion>` | Maven báo thiếu/không nhận modelVersion | XML phân biệt chữ hoa/thường; dùng đúng `modelVersion` |
| Đổi `modelVersion` thành phiên bản sản phẩm như `1.2.0` | Maven không hỗ trợ model đó | Dùng `4.0.0` cho POM thông thường hoặc `4.1.0` với Maven 4 phù hợp |
| Chỉ đổi `xmlns` sang `.../4.1.0`, giữ `modelVersion=4.0.0` | Namespace/schema/model không nhất quán; tool có thể báo lỗi | Chỉ migrate model có chủ đích và đồng bộ bộ khai báo |
| Đổi `http` thành `https` trong **namespace identifier** | Thay đổi URI định danh XML, dù chữ còn lại giống nhau | Giữ nguyên URI namespace Maven công bố |
| Thiếu `xmlns:xsi` nhưng có `xsi:schemaLocation` | XML parser báo prefix `xsi` chưa được khai báo | Thêm khai báo namespace cho `xsi` hoặc bỏ thuộc tính đó |
| Viết `xsi:schemaLocation` chỉ có một URL | Không đủ cặp namespace–XSD cho XML validator | Khai báo hai trường theo đúng thứ tự |
| Viết nhầm XSD của Maven 4 cho namespace Maven 3 | Schema validator/IDE có thể báo sai định dạng | Gắn đúng XSD với namespace/model |
| Thừa hoặc thiếu tag đóng, sai dấu ngoặc kép, ký tự `&` chưa escape | XML chưa well-formed, Maven không parse được | Sửa XML và kiểm tra bằng editor hoặc `xmllint` |
| Sửa `<project><version>` để “nâng modelVersion” | Chỉ làm đổi version artifact | Xác định thẻ `<version>` thuộc phạm vi nào |

### Ví dụ lỗi có thể quan sát

**Sai 1 — tên thẻ viết sai:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelversion>4.0.0</modelversion>
    <groupId>vn.example</groupId>
    <artifactId>demo</artifactId>
    <version>1.0.0</version>
</project>
```

Đây là XML well-formed nhưng không khai báo đúng `modelVersion`; Maven có thể báo lỗi mô hình hoặc thiếu trường bắt buộc. XML có phân biệt chữ hoa/thường nên `modelversion` không đồng nghĩa với `modelVersion`.

**Sai 2 — prefix chưa khai báo:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
</project>
```

Thiếu `xmlns:xsi`: parser xử lý XML namespace có thể báo “unbound prefix”. Thêm `xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"` đúng vào root.

**Sai 3 — nhầm schema với repository:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://repo.maven.apache.org/maven2">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>demo</artifactId>
    <version>1.0.0</version>
</project>
```

Về cú pháp XML, giá trị `schemaLocation` là một cặp URI; nhưng địa chỉ thứ hai ở đây **không phải file XSD**, vì vậy công cụ schema validation có thể thất bại. Khắc phục bằng `https://maven.apache.org/xsd/maven-4.0.0.xsd`. Repository Maven Central là nơi tải artifacts/plugin, không phải nơi XSD mặc định của POM.

### Chẩn đoán theo lớp

Khi gặp lỗi đầu file POM, đọc thông báo Maven và làm theo thứ tự:

1. Kiểm tra XML well-formed: tag, quote, escape, một root.
2. Kiểm tra `project`, `xmlns`, `xmlns:xsi`, `xsi:schemaLocation` có đúng mẫu version mong muốn.
3. Kiểm tra `modelVersion` và các tọa độ tối thiểu (kể cả kế thừa parent khi có).
4. Chạy `mvn -f pom.xml validate` để xem lỗi mô hình cụ thể. Khi thiếu parent hoặc repository không truy cập được, lỗi đó **không nhất thiết do namespace/XSD**.
5. Nếu IDE báo XSD nhưng Maven chạy được, kiểm tra chức năng XML validation, cache schema và mạng của IDE. Không sửa version Maven hoặc xóa repository chỉ vì thông báo của editor.

Các lỗi cụ thể có thể khác theo Maven phiên bản và plugin. Ví dụ `Non-parseable POM` thường liên quan cú pháp XML, `Unrecognised tag` có thể do phần tử sai vị trí/tên, còn `Non-resolvable parent POM` liên quan việc tìm parent. Cần đọc vị trí dòng/cột và nguyên văn log trước khi kết luận.

## 8. Bài tập tự kiểm tra

Cho một POM có khai báo:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.acme</groupId>
    <artifactId>catalog</artifactId>
    <version>2.4.0</version>
</project>
```

Hãy trả lời: (a) root là gì; (b) URI nào là default namespace; (c) thành phần thứ hai trong `schemaLocation` dùng làm gì; (d) `4.0.0` có chứng minh máy chạy Maven 4 không; (e) phiên bản của artifact là số nào?

**Đáp án:**

- (a) `project`.
- (b) `http://maven.apache.org/POM/4.0.0`.
- (c) Đường dẫn XSD mà XML validator/editor có thể dùng.
- (d) Không. `4.0.0` là POM model, muốn biết Maven runtime phải chạy `mvn --version` (hoặc Maven Wrapper).
- (e) `2.4.0`, tọa độ `vn.acme:catalog:2.4.0`.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference 4.0.0](https://maven.apache.org/pom.html)
- [Apache Maven — Frequently Asked Technical Questions: XSD](https://maven.apache.org/general.html)
- [Apache Maven — What's new in Maven 4? Model version 4.1.0](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [W3C — XML Namespaces](https://www.w3.org/TR/xml-names/)
- [W3C — XML Schema Instance Attributes](https://www.w3.org/TR/xmlschema-1/#xsi_schemaLocation)
