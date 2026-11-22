# Thay token bằng FilterSet và cú pháp token

Trong một dự án Java, nhiều file cấu hình hoặc tài liệu cần có những giá trị thay đổi theo môi trường và phiên bản phát hành. Ví dụ, cùng một mẫu `application.properties` có thể được dùng cho môi trường phát triển, kiểm thử và production; tên ứng dụng, địa chỉ dịch vụ hoặc phiên bản phát hành sẽ khác nhau ở mỗi lần đóng gói.

Apache Ant cung cấp **FilterSet** để thay các token được đánh dấu trong file nguồn bằng giá trị đã cấu hình. Người viết buildfile đặt token trong mẫu, khai báo ánh xạ token–giá trị trong FilterSet, rồi sử dụng FilterSet trong task hỗ trợ lọc như `copy`. Cách làm này giúp một mẫu văn bản có thể tạo ra nhiều file cấu hình phù hợp với từng môi trường.

## 1. Token là gì?

Token là một đoạn văn bản đánh dấu vị trí mà build cần thay thế bằng một giá trị khác. Với FilterSet mặc định của Ant, token được bao quanh bởi ký tự `@` ở hai đầu.

Ví dụ, file mẫu `application.properties.template`:

```properties
app.name=@APP_NAME@
app.version=@APP_VERSION@
app.environment=@ENVIRONMENT@
service.url=@SERVICE_URL@
```

Các chuỗi `@APP_NAME@`, `@APP_VERSION@`, `@ENVIRONMENT@` và `@SERVICE_URL@` là token. Chúng không phải cú pháp property của Ant; chúng là những vị trí thay thế được FilterSet nhận diện.

Nếu FilterSet khai báo:

| Token | Giá trị thay thế |
|---|---|
| `APP_NAME` | `inventory-service` |
| `APP_VERSION` | `2.4.1` |
| `ENVIRONMENT` | `production` |
| `SERVICE_URL` | `https://api.example.test` |

thì file đầu ra có nội dung tương ứng:

```properties
app.name=inventory-service
app.version=2.4.1
app.environment=production
service.url=https://api.example.test
```

FilterSet tìm phần token nằm giữa cặp dấu phân cách, tra giá trị đã khai báo và thay token bằng giá trị đó. Mọi vị trí xuất hiện của token được cấu hình trong nội dung được xử lý đều có thể được thay thế.

## 2. Khai báo FilterSet bằng filter

FilterSet là một Ant data type chứa một hoặc nhiều bộ lọc. Mỗi bộ lọc dùng phần tử `<filter>` với hai thuộc tính chính:

- `token`: tên token cần tìm, không bao gồm dấu phân cách ở đầu và cuối.
- `value`: giá trị văn bản sẽ thay cho token.

Ví dụ:

```xml
<filterset>
    <filter token="APP_NAME" value="inventory-service"/>
    <filter token="APP_VERSION" value="2.4.1"/>
    <filter token="ENVIRONMENT" value="production"/>
</filterset>
```

Với dấu phân cách mặc định `@`, FilterSet trên thay `@APP_NAME@`, `@APP_VERSION@` và `@ENVIRONMENT@` trong nội dung được lọc.

### 2.1. Kết hợp property của Ant với giá trị token

Giá trị của FilterSet thường lấy từ property để tránh ghi cứng cấu hình vào nhiều nơi:

```xml
<property name="app.name" value="inventory-service"/>
<property name="app.version" value="2.4.1"/>
<property name="environment" value="development"/>

<filterset>
    <filter token="APP_NAME" value="${app.name}"/>
    <filter token="APP_VERSION" value="${app.version}"/>
    <filter token="ENVIRONMENT" value="${environment}"/>
</filterset>
```

Ở đây có hai cơ chế thay thế khác nhau:

1. `${app.name}`, `${app.version}` và `${environment}` là tham chiếu property của Ant trong buildfile.
2. `@APP_NAME@`, `@APP_VERSION@` và `@ENVIRONMENT@` là token trong file văn bản được FilterSet xử lý.

Ant giải quyết property để tạo giá trị cho cấu hình FilterSet; sau đó task sử dụng FilterSet để thay token trong file nguồn. Không nên nhầm hai cú pháp này với nhau.

## 3. Sử dụng FilterSet trong task copy

Một cách sử dụng phổ biến là đặt FilterSet bên trong task `<copy>`. Task copy đọc file nguồn, thay các token đã cấu hình và ghi nội dung đã xử lý vào file đích.

Giả sử có file mẫu:

```text
src/main/config/application.properties.template
```

Ta muốn tạo file:

```text
build/config/application.properties
```

Buildfile có thể viết:

```xml
<project name="filterset-demo" default="prepare-config" basedir=".">

    <property name="app.name" value="inventory-service"/>
    <property name="app.version" value="2.4.1"/>
    <property name="environment" value="development"/>
    <property name="config.src" location="src/main/config"/>
    <property name="config.dest" location="build/config"/>

    <target name="prepare-config">
        <mkdir dir="${config.dest}"/>

        <copy file="${config.src}/application.properties.template"
              tofile="${config.dest}/application.properties"
              inputencoding="UTF-8"
              outputencoding="UTF-8">
            <filterset>
                <filter token="APP_NAME" value="${app.name}"/>
                <filter token="APP_VERSION" value="${app.version}"/>
                <filter token="ENVIRONMENT" value="${environment}"/>
            </filterset>
        </copy>
    </target>

</project>
```

Khi chạy:

```bash
ant prepare-config
```

Ant tạo thư mục đích, đọc file template, thay các token được khai báo rồi ghi file cấu hình đã xử lý. File nguồn vẫn là mẫu ban đầu; task copy tạo nội dung mới ở vị trí đích.

### 3.1. Sao chép nhiều file cùng dùng một FilterSet

Nếu một nhóm file văn bản cùng dùng token, có thể kết hợp FilterSet với FileSet:

```xml
<copy todir="build/config"
      inputencoding="UTF-8"
      outputencoding="UTF-8">
    <fileset dir="src/main/config/templates">
        <include name="**/*.properties.template"/>
        <include name="**/*.xml.template"/>
    </fileset>

    <filterset>
        <filter token="APP_NAME" value="${app.name}"/>
        <filter token="APP_VERSION" value="${app.version}"/>
        <filter token="ENVIRONMENT" value="${environment}"/>
    </filterset>
</copy>
```

Task copy xử lý các file được FileSet chọn và áp dụng FilterSet cho nội dung của chúng. Cách này phù hợp khi nhiều mẫu cấu hình chia sẻ cùng một bộ token.

Nếu chỉ muốn một số file được lọc, hãy giới hạn FileSet vào những file văn bản cần thay token. Không nên áp dụng FilterSet một cách rộng rãi cho mọi file trong thư mục chứa cả ảnh, JAR, ZIP hoặc dữ liệu nhị phân.

## 4. Dùng dấu phân cách token mặc định

Mặc định, FilterSet dùng `@` làm cả ký tự bắt đầu và kết thúc token. Vì vậy:

```text
@APP_NAME@
@BUILD_NUMBER@
@SERVICE_URL@
```

được hiểu là các token có tên lần lượt là `APP_NAME`, `BUILD_NUMBER` và `SERVICE_URL`.

Tên token trong FilterSet được khai báo không có dấu `@`:

```xml
<filterset>
    <filter token="APP_NAME" value="inventory-service"/>
</filterset>
```

Nếu file mẫu có chuỗi `@APP_NAME@`, FilterSet thay phần đó bằng `inventory-service`.

Token phải khớp với tên đã khai báo. Ví dụ `@APP_NAME@` và `@APP_NAME_VERSION@` là hai token khác nhau. Một token chưa có ánh xạ trong FilterSet thường được giữ nguyên trong đầu ra; điều này có thể giúp phát hiện cấu hình chưa được cung cấp, nhưng cũng có thể khiến file phát hành còn sót placeholder nếu không kiểm tra.

## 5. Thay đổi ký tự bắt đầu và kết thúc token

Nếu dấu `@` có thể xuất hiện thường xuyên trong file hoặc không phù hợp với quy ước của dự án, FilterSet cho phép thay đổi dấu phân cách bằng hai thuộc tính:

- `begintoken`: chuỗi bắt đầu token.
- `endtoken`: chuỗi kết thúc token.

Ví dụ dùng `@{` và `}`:

```xml
<filterset begintoken="@{" endtoken="}">
    <filter token="APP_NAME" value="inventory-service"/>
    <filter token="VERSION" value="2.4.1"/>
</filterset>
```

Với cấu hình trên, mẫu văn bản cần dùng cú pháp:

```text
app.name=@{APP_NAME}
app.version=@{VERSION}
```

FilterSet sẽ tìm token có dấu mở `@{` và dấu đóng `}`. Các giá trị trong thuộc tính `token` vẫn chỉ là tên token, không bao gồm dấu phân cách.

### 5.1. Vì sao cần chọn dấu phân cách phù hợp?

Một file có thể chứa nhiều chuỗi trông giống token nhưng mang ý nghĩa khác. Ví dụ, tài liệu có địa chỉ email `dev@example.test` hoặc cú pháp annotation, template của một framework khác. Nếu chọn dấu phân cách quá phổ biến, FilterSet có thể thay những đoạn văn bản không được dự định.

Một số nguyên tắc:

- Chọn cặp ký tự ít có khả năng xuất hiện tự nhiên trong file mẫu.
- Dùng cùng một quy ước token trong các mẫu thuộc cùng dự án.
- Không thay dấu phân cách trong buildfile mà quên cập nhật cú pháp ở file template.
- Nếu mẫu có nhiều hệ thống placeholder khác nhau, hãy tránh để FilterSet xử lý nhầm placeholder của hệ thống còn lại.

## 6. Nạp bộ lọc từ file cấu hình

Khi số lượng token lớn hoặc giá trị thay đổi theo môi trường, có thể tách ánh xạ token–giá trị ra file properties. FilterSet hỗ trợ thuộc tính `filtersfile` để nạp các bộ lọc từ file.

Ví dụ file `config/production.filters`:

```properties
APP_NAME=inventory-service
APP_VERSION=2.4.1
ENVIRONMENT=production
SERVICE_URL=https://api.example.test
```

Buildfile:

```xml
<copy file="src/application.properties.template"
      tofile="build/application.properties"
      inputencoding="UTF-8"
      outputencoding="UTF-8">
    <filterset filtersfile="config/production.filters"/>
</copy>
```

FilterSet đọc các cặp key/value từ file. Với key `APP_NAME`, token trong file mẫu vẫn có dạng `@APP_NAME@`; giá trị sau dấu `=` là nội dung thay thế.

### 6.1. Tách file lọc theo môi trường

Có thể duy trì một file cho mỗi môi trường:

```text
config/
├── development.filters
├── staging.filters
└── production.filters
```

Ví dụ `development.filters`:

```properties
ENVIRONMENT=development
SERVICE_URL=http://localhost:8080
```

Ví dụ `production.filters`:

```properties
ENVIRONMENT=production
SERVICE_URL=https://api.example.test
```

Buildfile có thể chọn file theo property:

```xml
<property name="environment" value="development"/>
<property name="filters.file" location="config/${environment}.filters"/>

<target name="prepare-config">
    <copy file="src/application.properties.template"
          tofile="build/application.properties"
          inputencoding="UTF-8"
          outputencoding="UTF-8">
        <filterset filtersfile="${filters.file}"/>
    </copy>
</target>
```

Chạy với mặc định:

```bash
ant prepare-config
```

Chọn staging:

```bash
ant -Denvironment=staging prepare-config
```

Chọn production:

```bash
ant -Denvironment=production prepare-config
```

Property `environment` quyết định tên file filters được nạp. Nhờ đó, cùng một file template có thể tạo cấu hình cho nhiều môi trường.

### 6.2. Kết hợp filtersfile với filter khai báo trực tiếp

Trong một FilterSet, có thể nạp bộ lọc từ file và bổ sung những token riêng bằng phần tử `<filter>`:

```xml
<filterset filtersfile="config/production.filters">
    <filter token="BUILD_NUMBER" value="${build.number}"/>
    <filter token="BUILD_DATE" value="${build.date}"/>
</filterset>
```

File filters chứa các giá trị cấu hình ổn định theo môi trường, còn buildfile bổ sung thông tin phát sinh theo lần build như số build hoặc ngày tạo. Khi cùng một token được khai báo nhiều nơi, cần tránh cấu hình trùng tên gây khó hiểu; hãy xác định một nguồn giá trị có thẩm quyền cho mỗi token.

## 7. Tái sử dụng FilterSet bằng id và refid

Nếu nhiều task copy cần dùng cùng một bộ lọc, có thể khai báo FilterSet một lần với `id` rồi tham chiếu bằng `refid`:

```xml
<filterset id="release.filters">
    <filter token="APP_NAME" value="${app.name}"/>
    <filter token="APP_VERSION" value="${app.version}"/>
    <filter token="ENVIRONMENT" value="${environment}"/>
</filterset>

<target name="copy-config">
    <copy file="src/config/application.properties.template"
          tofile="build/config/application.properties">
        <filterset refid="release.filters"/>
    </copy>

    <copy file="src/config/banner.txt.template"
          tofile="build/config/banner.txt">
        <filterset refid="release.filters"/>
    </copy>
</target>
```

Hai task copy sử dụng cùng bộ token. Nếu cần thay đổi giá trị `APP_VERSION`, chỉ cần cập nhật property được tham chiếu hoặc định nghĩa FilterSet tương ứng.

Khi dùng `refid`, phần tử FilterSet là tham chiếu đến cấu hình đã khai báo. Không đặt thêm các phần tử `<filter>` hoặc thuộc tính cấu hình khác trong cùng phần tử tham chiếu.

## 8. FilterSet và property của Ant khác nhau như thế nào?

Hai cơ chế đều có thể thay văn bản, nhưng chúng hoạt động ở những nơi và thời điểm khác nhau.

| Tiêu chí | Property của Ant | FilterSet |
|---|---|---|
| Cú pháp thường gặp | `${app.name}` | `@APP_NAME@` |
| Nội dung được xử lý | Giá trị trong buildfile và các vị trí hỗ trợ property expansion | Nội dung file được task hỗ trợ lọc xử lý |
| Cách khai báo | `<property name="app.name" value="..."/>` | `<filterset><filter token="APP_NAME" value="..."/></filterset>` |
| Mục đích | Quản lý cấu hình của quá trình build | Thay placeholder trong file đầu vào |
| Nơi sử dụng | Thuộc tính task, target, path, thông báo và cấu hình build | File template được copy hoặc xử lý bởi task hỗ trợ FilterSet |

Ví dụ kết hợp hai cơ chế:

```xml
<property name="app.version" value="3.2.0"/>

<copy file="src/version.txt.template" tofile="build/version.txt">
    <filterset>
        <filter token="VERSION" value="${app.version}"/>
    </filterset>
</copy>
```

Trong buildfile, `${app.version}` được thay bằng `3.2.0` để tạo giá trị cho filter. Trong file template, `@VERSION@` được thay bằng giá trị đó khi task copy áp dụng FilterSet.

Không nên mặc định rằng FilterSet sẽ tự thay mọi biểu thức `${...}` trong file template. Nếu muốn dùng cú pháp token của FilterSet, hãy đặt token theo dấu phân cách mà FilterSet đã cấu hình.

## 9. FilterSet không phải cơ chế thay thế nội dung tùy ý

FilterSet thay những token đã khai báo. Nó không phải một ngôn ngữ template đầy đủ và không tự thực hiện:

- Câu lệnh điều kiện như “nếu production thì dùng URL A”.
- Vòng lặp tạo nhiều dòng hoặc nhiều phần tử XML.
- Tính toán biểu thức hoặc gọi hàm trong token.
- Tìm kiếm và thay mọi chuỗi gần giống token nếu tên không khớp.
- Tự tải cấu hình bí mật từ hệ thống bên ngoài.

Nếu cần điều kiện, hãy dùng target, property hoặc task phù hợp để chọn file filters. Nếu cần xử lý cấu trúc phức tạp, có thể dùng công cụ template chuyên dụng hoặc một bước generate riêng.

Ví dụ chọn môi trường bằng property:

```xml
<property name="environment" value="development"/>

<condition property="environment.development">
    <equals arg1="${environment}" arg2="development"/>
</condition>

<target name="prepare-development" if="environment.development">
    <!-- Chuẩn bị cấu hình development. -->
</target>
```

Trong thực tế, điều kiện target của Ant kiểm tra sự tồn tại của property được nêu trong `if` hoặc `unless`; nó không trực tiếp so sánh chuỗi `environment` với `development`. Nếu cần chọn file filters theo giá trị, hãy xây dựng property đường dẫn hoặc dùng cơ chế điều kiện phù hợp với phiên bản Ant đang sử dụng.

## 10. Encoding và loại file cần lọc

FilterSet thay văn bản, vì vậy cần chú ý encoding khi đọc file nguồn và ghi file đích. Nếu template được lưu bằng UTF-8, nên cấu hình encoding tương ứng cho task copy:

```xml
<copy file="src/config/application.properties.template"
      tofile="build/config/application.properties"
      inputencoding="UTF-8"
      outputencoding="UTF-8">
    <filterset>
        <filter token="APP_NAME" value="inventory-service"/>
    </filterset>
</copy>
```

Nếu không chỉ định encoding, cách đọc/ghi có thể phụ thuộc encoding mặc định của môi trường chạy. Điều này có thể gây lỗi dấu tiếng Việt hoặc ký tự ngoài ASCII khi chuyển file giữa các máy.

### 10.1. Không lọc file nhị phân

Không nên áp dụng token filtering cho file nhị phân như:

- Ảnh PNG, JPEG, GIF.
- File JAR, WAR, ZIP.
- Font, audio, video hoặc file dữ liệu nhị phân.
- Các file đã nén hoặc được mã hóa theo định dạng riêng.

FilterSet xử lý nội dung theo cơ chế văn bản. Nếu task đọc và ghi một file nhị phân như văn bản, dữ liệu có thể bị thay đổi hoặc hỏng. Khi sao chép cả thư mục có nhiều loại file, hãy tách FileSet văn bản cần lọc khỏi FileSet nhị phân cần copy nguyên trạng.

Ví dụ:

```xml
<!-- Các mẫu văn bản được lọc token. -->
<copy todir="build/config"
      inputencoding="UTF-8"
      outputencoding="UTF-8">
    <fileset dir="src/config">
        <include name="**/*.properties.template"/>
        <include name="**/*.xml.template"/>
    </fileset>
    <filterset>
        <filter token="ENVIRONMENT" value="${environment}"/>
    </filterset>
</copy>

<!-- Tài nguyên nhị phân được sao chép nguyên trạng. -->
<copy todir="build/assets">
    <fileset dir="src/assets">
        <include name="**/*.png"/>
        <include name="**/*.jpg"/>
        <include name="**/*.woff2"/>
    </fileset>
</copy>
```

## 11. Những lỗi thường gặp khi dùng FilterSet

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Token vẫn còn nguyên trong file đầu ra | Token chưa được khai báo hoặc tên token không khớp | So sánh chính xác tên giữa template và `token` |
| Không có token nào được thay | FilterSet chưa được đặt trong task xử lý file hoặc task không hỗ trợ FilterSet | Kiểm tra task và vị trí nested `<filterset>` |
| Thay nhầm một đoạn văn bản | Dấu phân cách quá phổ biến hoặc token trùng với nội dung bình thường | Chọn delimiter riêng và tên token dễ nhận diện |
| Ký tự tiếng Việt bị lỗi | Encoding đọc hoặc ghi không phù hợp | Đặt `inputencoding` và `outputencoding` đúng với file |
| File ảnh hoặc JAR bị hỏng | Áp dụng text filtering lên dữ liệu nhị phân | Tách file văn bản và file nhị phân thành các nhóm copy riêng |
| Token không được thay dù property đã có | Nhầm `${property}` với `@TOKEN@` hoặc delimiter tùy chỉnh | Kiểm tra cú pháp token và `begintoken`/`endtoken` |
| File filters không được nạp | Đường dẫn `filtersfile` sai hoặc file không tồn tại | Kiểm tra đường dẫn và cấu hình xử lý file filters bị thiếu |
| Cấu hình môi trường không đúng | Build nạp nhầm file filters hoặc property chọn môi trường có giá trị khác | In property môi trường và đường dẫn filters ra log |

### 11.1. Kiểm tra token chưa được thay

Sau khi tạo file cấu hình, có thể dùng task `loadfile` để đọc nội dung vào property và in ra log trong môi trường phát triển:

```xml
<target name="show-generated-config">
    <loadfile property="generated.config"
              srcFile="build/config/application.properties"
              encoding="UTF-8"/>
    <echo message="${generated.config}"/>
</target>
```

Không nên in file cấu hình production có chứa mật khẩu, token truy cập hoặc dữ liệu nhạy cảm ra log CI. Khi chỉ cần xác nhận token đã được thay, hãy kiểm tra một file thử nghiệm không chứa bí mật hoặc dùng một bước xác minh chỉ in những trường an toàn.

### 11.2. Token không khớp do delimiter tùy chỉnh

Nếu FilterSet khai báo:

```xml
<filterset begintoken="@{" endtoken="}">
    <filter token="APP_NAME" value="inventory-service"/>
</filterset>
```

thì cú pháp token mong đợi trong file nguồn là `@{APP_NAME}`. Nếu file vẫn dùng `@APP_NAME@`, FilterSet sẽ không tìm thấy token theo dấu phân cách mới.

Tránh dùng `${` làm dấu mở nếu file template còn chứa property placeholder `${...}` của Ant hoặc cú pháp của một hệ thống template khác. Giữ delimiter mặc định `@...@` hoặc chọn một cặp ký tự riêng ít xung đột thường dễ bảo trì hơn.

## 12. Ví dụ hoàn chỉnh: tạo cấu hình cho nhiều môi trường

Giả sử dự án có cấu trúc:

```text
application/
├── build.xml
├── config/
│   ├── development.filters
│   ├── staging.filters
│   └── production.filters
├── src/
│   └── config/
│       ├── application.properties.template
│       └── logback.xml.template
└── build/
```

File mẫu `application.properties.template`:

```properties
app.name=@APP_NAME@
app.version=@APP_VERSION@
environment=@ENVIRONMENT@
service.url=@SERVICE_URL@
```

File `config/development.filters`:

```properties
APP_NAME=inventory-service
APP_VERSION=2.4.1-SNAPSHOT
ENVIRONMENT=development
SERVICE_URL=http://localhost:8080
```

File `config/production.filters`:

```properties
APP_NAME=inventory-service
APP_VERSION=2.4.1
ENVIRONMENT=production
SERVICE_URL=https://api.example.test
```

Buildfile:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory-service" default="prepare-config" basedir=".">

    <property name="environment" value="development"/>
    <property name="filters.file" location="config/${environment}.filters"/>
    <property name="template.dir" location="src/config"/>
    <property name="config.dir" location="build/config"/>

    <target name="prepare-config">
        <mkdir dir="${config.dir}"/>

        <copy todir="${config.dir}"
              inputencoding="UTF-8"
              outputencoding="UTF-8">
            <fileset dir="${template.dir}">
                <include name="*.template"/>
            </fileset>
            <filterset filtersfile="${filters.file}"/>
            <mapper type="glob" from="*.template" to="*"/>
        </copy>
    </target>

</project>
```

Chạy cho development:

```bash
ant prepare-config
```

Chạy cho staging:

```bash
ant -Denvironment=staging prepare-config
```

Chạy cho production:

```bash
ant -Denvironment=production prepare-config
```

Trong mỗi lượt chạy, Ant chọn file filters tương ứng, đọc các template và tạo file cấu hình trong `build/config`. Mapper bỏ hậu tố `.template`, vì vậy `application.properties.template` trở thành `application.properties` và `logback.xml.template` trở thành `logback.xml`. Các file template trong `src/config` không bị sửa. Nếu file filters của một môi trường không tồn tại, task sẽ báo lỗi theo cấu hình xử lý file filters; vì vậy cần cung cấp file cho mọi môi trường được hỗ trợ.

Trong môi trường thật, không lưu mật khẩu hoặc secret trực tiếp trong file filters được quản lý cùng mã nguồn. Hãy lấy giá trị nhạy cảm từ cơ chế secret của CI hoặc môi trường triển khai, hạn chế quyền truy cập và không in chúng ra log.

## 13. Nguyên tắc sử dụng FilterSet dễ bảo trì

- Đặt token có tên rõ ràng, ví dụ `APP_VERSION`, `SERVICE_URL`, `ENVIRONMENT`.
- Dùng cùng một delimiter trong toàn bộ nhóm template.
- Khai báo FilterSet một lần và tái sử dụng bằng `id`/`refid` khi nhiều task cần cùng cấu hình.
- Dùng file filters riêng cho các môi trường khi giá trị thay đổi theo môi trường.
- Kết hợp property Ant để quản lý giá trị cấu hình và đường dẫn file filters.
- Chỉ lọc file văn bản; copy file nhị phân nguyên trạng.
- Chỉ định encoding rõ ràng nếu file chứa ký tự ngoài ASCII.
- Kiểm tra token chưa được thay trước khi đóng gói sản phẩm.
- Tránh để các placeholder của hệ thống template khác bị FilterSet xử lý nhầm.
- Không đưa mật khẩu, API key hoặc secret vào file filters được commit hoặc log.

## 14. Kết luận

FilterSet cho phép Apache Ant thay token trong nội dung file bằng các giá trị đã khai báo. Mỗi filter ánh xạ một tên token với một giá trị; mặc định token có dạng `@TOKEN@`, nhưng có thể đổi dấu phân cách bằng `begintoken` và `endtoken`. Bộ lọc có thể khai báo trực tiếp, nạp từ file properties hoặc tái sử dụng qua `id` và `refid`.

Khi kết hợp FilterSet với task `copy`, một file template có thể tạo ra nhiều file cấu hình theo môi trường mà không cần sửa file nguồn. Hãy phân biệt cú pháp token với property `${...}` của Ant, chọn delimiter phù hợp, chỉ lọc file văn bản và kiểm soát encoding. Tổ chức FilterSet rõ ràng giúp quá trình tạo cấu hình lặp lại được, dễ thay đổi và ít sai khác giữa các môi trường.
