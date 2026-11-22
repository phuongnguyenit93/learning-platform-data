# Sao chép tài nguyên có lọc và tách tệp văn bản khỏi tệp nhị phân

Trong một dự án Java, thư mục tài nguyên thường chứa nhiều loại tệp: cấu hình `.properties`, XML, HTML, văn bản hướng dẫn, hình ảnh, phông chữ và các tệp nhị phân khác. Khi tạo gói phát hành, ta thường cần sao chép các tệp này sang thư mục đầu ra. Một số tệp văn bản cần thay placeholder bằng giá trị của build, chẳng hạn phiên bản ứng dụng hoặc địa chỉ dịch vụ. Các tệp nhị phân cần được sao chép nguyên vẹn.

Apache Ant cung cấp task `<copy>` cùng các cơ chế lọc nội dung:

- `filterset` thay thế token trong nội dung tệp, ví dụ `@APP_VERSION@` thành `1.2.0`.
- `filterchain` áp dụng một chuỗi bộ lọc để biến đổi nội dung khi sao chép.
- Thuộc tính `filtering="true"` bật bộ lọc toàn cục được khai báo bằng task `<filter>`.

Điểm quan trọng là phải xác định rõ tệp nào là văn bản cần lọc và tệp nào là nhị phân cần giữ nguyên. Nếu áp dụng bộ lọc văn bản lên ảnh, tệp JAR, PDF hoặc dữ liệu nhị phân khác, nội dung có thể bị thay đổi và tệp đầu ra không còn sử dụng được.

Sau bài học, bạn có thể:

- Sao chép tài nguyên bằng task `<copy>` và FileSet.
- Thay token trong tệp văn bản bằng `filterset`.
- Dùng bộ lọc toàn cục qua `<filter>` và `filtering="true"`.
- Biến đổi nội dung bằng `filterchain`.
- Tách riêng bước sao chép văn bản và nhị phân.
- Tổ chức include/exclude để tránh lọc nhầm ảnh, font, archive hoặc tệp thực thi.

## 1. Sao chép tài nguyên bằng task `<copy>`

Task `<copy>` sao chép một tệp hoặc một nhóm tài nguyên đến vị trí đích. Với một tệp cụ thể, có thể dùng thuộc tính `file` và `tofile`:

```xml
<copy file="src/config/app.properties"
      tofile="build/config/app.properties" />
```

Với nhiều tệp, dùng `fileset` và chỉ định thư mục đích bằng `todir`:

```xml
<copy todir="build/resources">
    <fileset dir="src/main/resources">
        <include name="**/*" />
    </fileset>
</copy>
```

FileSet chọn các tệp bên dưới `src/main/resources`. Task copy giữ cấu trúc đường dẫn tương đối khi đặt chúng vào `build/resources`.

Ví dụ, nếu nguồn có cấu trúc:

```text
src/main/resources/
├── app.properties
├── messages/
│   └── vi.txt
└── images/
    └── logo.png
```

thì thư mục đích có cấu trúc tương ứng:

```text
build/resources/
├── app.properties
├── messages/
│   └── vi.txt
└── images/
    └── logo.png
```

### 1.1. Chọn tệp bằng `include` và `exclude`

FileSet cho phép chọn tệp theo mẫu tên hoặc đường dẫn. Ví dụ, chỉ sao chép XML và properties:

```xml
<copy todir="build/config">
    <fileset dir="src/main/resources">
        <include name="**/*.xml" />
        <include name="**/*.properties" />
        <exclude name="**/local/**" />
    </fileset>
</copy>
```

Mẫu `**/*.xml` chọn tệp XML ở mọi cấp thư mục; `**/*.properties` chọn tệp properties; `exclude` loại các tệp nằm trong thư mục `local` ở bất kỳ cấp nào.

Các mẫu được tính tương đối với thư mục `dir` của FileSet. Khi tách nhóm văn bản và nhị phân, hãy dùng các mẫu cụ thể thay vì chọn toàn bộ `**/*` rồi áp dụng bộ lọc văn bản cho tất cả.

### 1.2. Các thuộc tính thường dùng của `copy`

| Thuộc tính | Ý nghĩa |
|---|---|
| `file` | Tệp nguồn cụ thể cần sao chép. |
| `tofile` | Đường dẫn của tệp đích khi sao chép một nguồn thành một tệp. |
| `todir` | Thư mục đích khi sao chép một hoặc nhiều nguồn. |
| `overwrite` | Buộc ghi đè tệp đích nếu tệp nguồn đã tồn tại. |
| `preservelastmodified` | Giữ thời điểm sửa đổi của tệp nguồn cho tệp đích. |
| `flatten` | Bỏ cấu trúc thư mục tương đối khi sao chép vào thư mục đích. |
| `filtering` | Bật các bộ lọc toàn cục được khai báo bằng task `<filter>`. |
| `failonerror` | Quyết định build có thất bại khi thao tác sao chép gặp lỗi hay không. |

Ví dụ:

```xml
<copy todir="build/resources"
      overwrite="true"
      preservelastmodified="true">
    <fileset dir="src/main/resources">
        <include name="**/*.properties" />
    </fileset>
</copy>
```

`overwrite="true"` hữu ích khi muốn cập nhật đầu ra theo nguồn trong mỗi lần build. `preservelastmodified="true"` giữ lại timestamp của nguồn, có thể hữu ích với công cụ phía sau dựa vào thời điểm sửa đổi.

## 2. Lọc token trong tệp văn bản bằng `filterset`

FilterSet thay thế các token trong nội dung tệp. Theo mặc định, token được bao quanh bởi dấu `@` ở hai phía.

Ví dụ, tệp nguồn `src/main/resources/app.properties` có nội dung:

```properties
app.name=SampleApp
app.version=@APP_VERSION@
api.baseUrl=@API_BASE_URL@
```

Trong buildfile, khai báo các giá trị cần thay:

```xml
<copy todir="build/resources">
    <fileset dir="src/main/resources">
        <include name="app.properties" />
    </fileset>
    <filterset>
        <filter token="APP_VERSION" value="1.2.0" />
        <filter token="API_BASE_URL" value="https://api.example.com" />
    </filterset>
</copy>
```

Tệp đầu ra có nội dung:

```properties
app.name=SampleApp
app.version=1.2.0
api.baseUrl=https://api.example.com
```

Trong đó:

- `token` là tên token, không cần ghi dấu `@` bao quanh.
- `value` là nội dung thay thế.
- `filterset` chứa một hoặc nhiều cặp token/value.

FilterSet được đặt bên trong task copy nên các tệp được task xử lý sẽ nhận phép thay thế tương ứng. Vì vậy, cần giới hạn FileSet ở những tệp văn bản thực sự cần thay token.

### 2.1. Thay đổi dấu phân cách token

Nếu nội dung văn bản đã dùng `@...@` cho mục đích khác, có thể chọn dấu phân cách riêng bằng `begintoken` và `endtoken`:

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="app.properties" />
    </fileset>
    <filterset begintoken="${" endtoken="}">
        <filter token="app.version" value="${app.version}" />
        <filter token="build.name" value="${build.name}" />
    </filterset>
</copy>
```

Với cấu hình này, nội dung nguồn có thể dùng `${app.version}` và `${build.name}` làm token để Ant thay thế. Hãy chọn dấu phân cách phù hợp với định dạng tệp và các placeholder vốn đã được ứng dụng sử dụng.

### 2.2. Nạp token từ tệp cấu hình

Không nhất thiết phải viết tất cả token trong `build.xml`. Có thể lưu cặp token/value trong một tệp filter:

Tệp `filters/release.properties`:

```properties
APP_VERSION=1.2.0
API_BASE_URL=https://api.example.com
```

Buildfile:

```xml
<copy todir="build/resources">
    <fileset dir="src/main/resources">
        <include name="**/*.properties" />
        <include name="**/*.xml" />
    </fileset>
    <filterset>
        <filtersfile file="filters/release.properties" />
    </filterset>
</copy>
```

`filtersfile` nạp các cặp token/value từ tệp. Cách này giúp tách cấu hình theo môi trường, ví dụ `development.properties`, `staging.properties` và `production.properties`.

Hãy quản lý các tệp filter như dữ liệu cấu hình thông thường. Không đưa mật khẩu, token truy cập hoặc khóa bí mật vào tệp được commit công khai hoặc vào nội dung đầu ra không được bảo vệ.

### 2.3. Dùng property của Ant làm giá trị thay thế

Giá trị thay thế có thể lấy từ property đã được khai báo:

```xml
<project name="filtered-copy" default="copy-text">
    <property name="app.version" value="2.4.1" />
    <property name="api.base.url" value="https://api.example.com" />

    <target name="copy-text">
        <copy todir="build/resources">
            <fileset dir="src/main/resources">
                <include name="**/*.properties" />
            </fileset>
            <filterset>
                <filter token="APP_VERSION" value="${app.version}" />
                <filter token="API_BASE_URL" value="${api.base.url}" />
            </filterset>
        </copy>
    </target>
</project>
```

Có thể truyền giá trị khác từ dòng lệnh:

```bash
ant -Dapp.version=2.5.0 -Dapi.base.url=https://staging.example.com copy-text
```

Do property thông thường của Ant chỉ được đặt một lần, giá trị truyền bằng `-D` đã tồn tại trước khi các giá trị mặc định trong buildfile được xử lý và sẽ được giữ lại.

## 3. Bộ lọc toàn cục: `<filter>` và `filtering="true"`

Task `<filter>` khai báo một cặp token/value trong bộ lọc toàn cục của project. Task `<copy>` chỉ áp dụng các bộ lọc toàn cục đó khi bật `filtering="true"`.

Ví dụ:

```xml
<project name="global-filter-demo" default="copy-config">
    <property name="app.version" value="1.2.0" />
    <filter token="APP_VERSION" value="${app.version}" />
    <filter token="BUILD_LABEL" value="release" />

    <target name="copy-config">
        <copy todir="build/config" filtering="true">
            <fileset dir="src/config">
                <include name="**/*.properties" />
            </fileset>
        </copy>
    </target>
</project>
```

Các tệp nguồn có thể chứa `@APP_VERSION@` hoặc `@BUILD_LABEL@`. Khi task copy chạy với `filtering="true"`, Ant áp dụng bộ lọc toàn cục và thay token tương ứng.

Phân biệt hai cách khai báo:

| Cơ chế | Phạm vi | Cách bật |
|---|---|---|
| `<filter>` | Khai báo token/value toàn cục trong project. | Task copy đặt `filtering="true"` để áp dụng bộ lọc toàn cục. |
| `<filterset>` lồng trong `<copy>` | Bộ token/value gắn với task copy cụ thể. | Khai báo trực tiếp bên trong task. |

Với cấu hình theo môi trường hoặc theo từng nhóm tệp, FilterSet lồng trong task thường giúp phạm vi áp dụng dễ nhìn hơn. Bộ lọc toàn cục phù hợp khi nhiều task copy cần cùng một tập token.

## 4. Biến đổi nội dung bằng `filterchain`

FilterSet tập trung vào thay token. `filterchain` là chuỗi các bộ lọc nội dung (FilterReader) được áp dụng khi task đọc dữ liệu. Nó phù hợp với những phép biến đổi văn bản như thay token, mở rộng property, chọn dòng hoặc xử lý khoảng trắng.

Ví dụ dùng `replacetokens` trong filterchain:

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="app.properties" />
    </fileset>
    <filterchain>
        <replacetokens>
            <token key="APP_VERSION" value="${app.version}" />
            <token key="ENVIRONMENT" value="${environment}" />
        </replacetokens>
    </filterchain>
</copy>
```

Với `replacetokens`, token mặc định được bao quanh bằng `@`. Ví dụ, `@APP_VERSION@` được thay bằng giá trị property `app.version`.

### 4.1. Mở rộng property trong nội dung bằng `expandproperties`

Nếu tệp nguồn chứa trực tiếp cú pháp `${property.name}`, có thể dùng bộ lọc `<expandproperties/>`:

Tệp nguồn `src/config/app.properties`:

```properties
app.version=${app.version}
app.environment=${environment}
```

Buildfile:

```xml
<property name="app.version" value="2.4.1" />
<property name="environment" value="staging" />

<target name="copy-config">
    <copy todir="build/config">
        <fileset dir="src/config">
            <include name="**/*.properties" />
        </fileset>
        <filterchain>
            <expandproperties />
        </filterchain>
    </copy>
</target>
```

Kết quả trong tệp đích:

```properties
app.version=2.4.1
app.environment=staging
```

Chỉ dùng `expandproperties` cho tệp văn bản có chủ đích chứa property reference của Ant. Nếu nội dung cần giữ nguyên `${...}` để ứng dụng khác xử lý, không áp dụng bộ lọc này cho tệp đó.

### 4.2. Kết hợp nhiều bộ lọc theo thứ tự

Một filterchain có thể chứa nhiều bộ lọc. Chúng được khai báo theo thứ tự xử lý, nên đầu ra của bộ lọc trước trở thành đầu vào của bộ lọc sau.

Ví dụ:

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="message.txt" />
    </fileset>
    <filterchain>
        <replacetokens>
            <token key="APP_NAME" value="SampleApp" />
        </replacetokens>
        <striplinebreaks />
    </filterchain>
</copy>
```

Trong ví dụ, Ant thay token trước, sau đó `striplinebreaks` loại các ký tự xuống dòng theo hành vi của bộ lọc. Bộ lọc thứ hai vì vậy nhận nội dung đã được thay token. Chỉ thêm những bước biến đổi thật sự cần thiết; một filterchain quá dài có thể khiến việc hiểu kết quả khó hơn.

## 5. Vì sao phải tách tệp văn bản và tệp nhị phân?

Tệp văn bản biểu diễn nội dung dưới dạng ký tự theo một encoding như UTF-8. Bộ lọc token có thể đọc nội dung, tìm chuỗi và thay thế bằng giá trị khác.

Tệp nhị phân chứa byte theo định dạng riêng. Các byte có thể biểu diễn pixel ảnh, cấu trúc PDF, dữ liệu nén, lớp Java, âm thanh hoặc phông chữ. Chúng không phải văn bản thông thường.

Ví dụ:

| Nhóm | Ví dụ thường gặp | Có nên áp dụng lọc văn bản? |
|---|---|---|
| Văn bản cấu hình | `.properties`, `.xml`, `.yml`, `.json` | Có thể, nếu nội dung có token cần thay. |
| Văn bản giao diện | `.html`, `.css`, `.js`, `.txt` | Có thể, nếu đã xác định placeholder và phạm vi thay thế. |
| Mã nguồn | `.java`, `.kt` | Chỉ khi có nhu cầu cụ thể; thường nên biên dịch mã nguồn riêng thay vì thay token tùy tiện. |
| Hình ảnh | `.png`, `.jpg`, `.gif`, `.ico` | Không. Sao chép nguyên byte. |
| Archive và thư viện | `.zip`, `.jar`, `.war` | Không. Sao chép nguyên byte hoặc dùng task archive chuyên dụng. |
| Tài liệu nhị phân | `.pdf`, `.docx`, `.xlsx` | Không. |
| Font và media | `.woff`, `.ttf`, `.mp3`, `.mp4` | Không. |
| Bytecode | `.class` | Không. |

Danh sách phần mở rộng chỉ là gợi ý. Một định dạng như SVG thường là XML dạng văn bản, còn một số tệp có phần mở rộng `.dat` có thể là nhị phân. Hãy phân loại dựa trên định dạng và cách sử dụng thực tế, không chỉ dựa vào tên tệp.

Nếu filterset hoặc filterchain được áp dụng lên tệp nhị phân, quá trình đọc và ghi như văn bản có thể làm thay đổi byte, gây hỏng tệp hoặc khiến ứng dụng không đọc được. Vì vậy, tách task copy thành hai nhóm riêng giúp kiểm soát chính xác nhóm nào được lọc.

## 6. Tách bước sao chép văn bản và nhị phân

Giả sử thư mục tài nguyên có cấu trúc:

```text
src/main/resources/
├── app.properties
├── messages/
│   └── vi.txt
├── templates/
│   └── index.html
├── images/
│   ├── logo.png
│   └── banner.jpg
├── fonts/
│   └── app.woff2
└── lib/
    └── helper.jar
```

Ta chia thành hai target hoặc hai task copy:

1. Nhóm văn bản: chọn đúng phần mở rộng cần thay token và áp dụng filterset.
2. Nhóm nhị phân: chọn ảnh, font, archive và các tệp nhị phân khác; không gắn filterset hoặc filterchain.

Ví dụ:

```xml
<project name="resource-copy" default="copy-resources" basedir=".">
    <property name="resources.dir" location="src/main/resources" />
    <property name="dist.resources.dir" location="build/resources" />
    <property name="app.version" value="1.2.0" />
    <property name="environment" value="production" />

    <target name="copy-text-resources">
        <copy todir="${dist.resources.dir}" overwrite="true">
            <fileset dir="${resources.dir}">
                <include name="**/*.properties" />
                <include name="**/*.xml" />
                <include name="**/*.yml" />
                <include name="**/*.yaml" />
                <include name="**/*.json" />
                <include name="**/*.html" />
                <include name="**/*.txt" />
            </fileset>
            <filterset>
                <filter token="APP_VERSION" value="${app.version}" />
                <filter token="ENVIRONMENT" value="${environment}" />
            </filterset>
        </copy>
    </target>

    <target name="copy-binary-resources">
        <copy todir="${dist.resources.dir}" overwrite="true">
            <fileset dir="${resources.dir}">
                <include name="**/*.png" />
                <include name="**/*.jpg" />
                <include name="**/*.jpeg" />
                <include name="**/*.gif" />
                <include name="**/*.ico" />
                <include name="**/*.woff" />
                <include name="**/*.woff2" />
                <include name="**/*.ttf" />
                <include name="**/*.jar" />
                <include name="**/*.zip" />
                <include name="**/*.pdf" />
            </fileset>
        </copy>
    </target>

    <target name="copy-resources"
            depends="copy-text-resources,copy-binary-resources" />
</project>
```

Target `copy-text-resources` chỉ chọn những phần mở rộng được xem là văn bản và cần thay token. Target `copy-binary-resources` chọn các loại nhị phân và không khai báo bộ lọc. Target `copy-resources` điều phối cả hai bước.

### 6.1. Vì sao hai task copy dùng cùng thư mục đích?

Hai FileSet có thể chọn các tệp khác nhau nhưng cùng giữ cấu trúc thư mục tương đối. Vì thế, chúng có thể ghi vào cùng `build/resources` mà không làm thay đổi nội dung của nhau, miễn là các mẫu chọn không chồng lấn.

Nếu một tệp có thể khớp cả hai nhóm, cần sửa mẫu hoặc loại trừ rõ ràng để tệp đó chỉ được xử lý theo một cách. Ví dụ, không nên để một tệp `.svg` vừa nằm trong nhóm văn bản cần thay token vừa bị xem là một tệp nhị phân chỉ vì nó được dùng làm hình ảnh. SVG là định dạng XML dạng văn bản; chỉ lọc nó nếu thật sự cần thay placeholder bên trong.

### 6.2. Chọn lọc theo thư mục thay vì phần mở rộng

Nếu dự án đã tổ chức tài nguyên thành thư mục riêng, có thể chia theo cấu trúc:

```text
resources/
├── filtered-text/
│   ├── app.properties
│   └── index.html
└── binary/
    ├── logo.png
    └── app.woff2
```

Khi đó, các FileSet đơn giản hơn:

```xml
<copy todir="build/resources">
    <fileset dir="resources/filtered-text" />
    <filterset>
        <filter token="APP_VERSION" value="${app.version}" />
    </filterset>
</copy>

<copy todir="build/resources">
    <fileset dir="resources/binary" />
</copy>
```

Phân nhóm theo thư mục phù hợp khi nhóm tài nguyên có quy tắc xử lý ổn định. Nếu nguồn do nhiều nhóm phát triển quản lý và không thể đổi cấu trúc, phân nhóm bằng `include`/`exclude` theo phần mở rộng có thể thuận tiện hơn.

## 7. Dùng bộ lọc toàn cục hay FilterSet cục bộ?

Hai cơ chế có thể giải quyết cùng nhu cầu thay token, nhưng phạm vi sử dụng khác nhau.

### FilterSet cục bộ

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="app.properties" />
    </fileset>
    <filterset>
        <filter token="APP_VERSION" value="${app.version}" />
    </filterset>
</copy>
```

Các token được khai báo ngay tại task copy cần sử dụng chúng. Cách này giúp người đọc nhìn thấy rõ nhóm tệp nào nhận bộ lọc nào.

### Bộ lọc toàn cục

```xml
<filter token="APP_VERSION" value="${app.version}" />

<copy todir="build/config" filtering="true">
    <fileset dir="src/config">
        <include name="**/*.properties" />
    </fileset>
</copy>
```

Các cặp token/value được đăng ký ở cấp project và task copy bật `filtering="true"` để áp dụng chúng. Cách này tiện khi nhiều bước copy cần dùng chung cấu hình.

| Tiêu chí | FilterSet cục bộ | Bộ lọc toàn cục |
|---|---|---|
| Khai báo | Bên trong task copy. | Bằng task `<filter>` trong project. |
| Bật lọc | Có FilterSet lồng trong task. | Đặt `filtering="true"` trên copy. |
| Phạm vi | Task copy cụ thể. | Các task copy bật lọc toàn cục. |
| Dễ đọc khi | Mỗi nhóm tệp có token khác nhau. | Nhiều task dùng chung token. |

## 8. Những điều cần chú ý khi thay token

### 8.1. Token có thể xuất hiện ngoài ý muốn

Nếu token quá chung, ví dụ `@NAME@`, nó có thể xuất hiện trong tài liệu hướng dẫn, ví dụ mã hoặc nội dung người dùng muốn giữ nguyên. Khi đó FilterSet có thể thay cả những vị trí không mong muốn.

Hãy chọn tên token có ý nghĩa và ít có khả năng trùng, ví dụ:

```text
@APP_RELEASE_VERSION@
@PUBLIC_API_BASE_URL@
@BUILD_COMMIT_ID@
```

Chỉ áp dụng filterset cho những tệp có quy ước placeholder rõ ràng.

### 8.2. Giá trị thay thế có thể chứa ký tự đặc biệt

Giá trị thay thế được ghi vào nội dung tệp. Hãy bảo đảm giá trị phù hợp với định dạng đích. Ví dụ, nếu thay token trong XML, giá trị có dấu `&` hoặc `<` phải được escape theo quy tắc XML; FilterSet không tự bảo đảm giá trị thay thế là XML hợp lệ.

Tương tự, khi thay token trong JSON, giá trị chứa dấu nháy kép, dấu gạch chéo ngược hoặc ký tự điều khiển phải được escape theo cú pháp JSON. Nếu cần tạo JSON, nên dùng giá trị đã được mã hóa phù hợp thay vì đưa trực tiếp chuỗi tùy ý.

### 8.3. Không thay thế placeholder thuộc hệ thống khác

Một số định dạng sử dụng cú pháp riêng như `${ENV_VAR}`, `{{name}}`, `%NAME%` hoặc `@token@`. Nếu một tệp cần giữ placeholder để ứng dụng hoặc nền tảng khác xử lý lúc chạy, đừng áp dụng filterchain hoặc filterset có thể thay placeholder đó.

Ví dụ, nếu cấu hình cần giữ nguyên `${DATABASE_URL}` cho môi trường triển khai, không dùng `expandproperties` trên tệp đó trừ khi Ant thực sự được giao nhiệm vụ thay giá trị này.

### 8.4. Mã hóa ký tự và nội dung Unicode

Khi lọc văn bản, encoding đầu vào và đầu ra có thể ảnh hưởng đến dấu tiếng Việt và các ký tự Unicode. Hãy thống nhất encoding của tệp nguồn và kiểm tra khả năng cấu hình encoding của task/bộ lọc trong phiên bản Ant đang sử dụng. Không giả định mọi tệp đều là UTF-8 chỉ vì chúng có phần mở rộng `.txt` hoặc `.properties`.

Nếu tệp nguồn dùng một encoding cũ, cần xác định encoding đó trước khi chuyển đổi hoặc lọc. Khi có thể, chuẩn hóa tệp văn bản của dự án sang UTF-8 để giảm khác biệt giữa các máy build.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Token vẫn xuất hiện nguyên dạng trong tệp đích | Token không khớp tên, dấu phân cách khác hoặc bộ lọc toàn cục chưa bật. | Kiểm tra `token`, `begintoken`, `endtoken` và `filtering="true"` nếu dùng global filters. |
| Token bị thay ở tệp không mong muốn | FileSet chọn quá rộng hoặc bộ lọc được áp dụng cho cả nhóm. | Tách FileSet hoặc task copy theo nhóm văn bản cần lọc. |
| Ảnh hoặc JAR không mở được sau khi copy | Filterset/filterchain đã xử lý dữ liệu nhị phân như văn bản. | Sao chép nhị phân bằng task riêng không gắn bộ lọc. |
| Kết quả XML/JSON không hợp lệ | Giá trị thay thế chứa ký tự cần escape theo định dạng đích. | Mã hóa/escape giá trị thay thế theo cú pháp XML hoặc JSON. |
| Dấu tiếng Việt bị lỗi | Encoding nguồn và cách đọc/ghi không khớp. | Chuẩn hóa UTF-8 và cấu hình encoding phù hợp. |
| Tệp đích chứa placeholder của hệ thống khác nhưng bị thay mất | Bộ lọc mở rộng cú pháp placeholder mà ứng dụng cần giữ. | Không áp dụng bộ lọc đó cho tệp, hoặc chọn token riêng không trùng cú pháp của ứng dụng. |
| Tệp đích không cập nhật | Task copy bỏ qua tệp đích đã mới hơn hoặc không cần ghi đè theo cấu hình. | Kiểm tra timestamp và cân nhắc `overwrite="true"` nếu cần. |
| Tệp bị đặt sai vị trí | Dùng `flatten` hoặc mẫu nguồn không như dự kiến. | Kiểm tra `todir`, cấu trúc FileSet và thuộc tính `flatten`. |

## 10. Ví dụ tổng hợp: cấu hình theo môi trường

Giả sử ứng dụng có hai tệp nguồn:

`src/main/resources/config/app.properties`:

```properties
app.name=SampleApp
app.version=@APP_VERSION@
environment=@ENVIRONMENT@
api.url=@API_BASE_URL@
```

`src/main/resources/config/banner.txt`:

```text
Welcome to @APP_NAME@ version @APP_VERSION@
```

Và thư mục tài nguyên nhị phân:

```text
src/main/resources/
├── config/
│   ├── app.properties
│   └── banner.txt
└── static/
    ├── logo.png
    └── fonts/
        └── app.woff2
```

Buildfile:

```xml
<project name="filtered-resources" default="prepare-resources" basedir=".">
    <property name="resources.dir" location="src/main/resources" />
    <property name="dist.dir" location="build/resources" />

    <property name="app.version" value="1.0.0" />
    <property name="app.name" value="SampleApp" />
    <property name="environment" value="development" />
    <property name="api.base.url" value="https://dev-api.example.com" />

    <target name="copy-text">
        <copy todir="${dist.dir}" overwrite="true">
            <fileset dir="${resources.dir}">
                <include name="**/*.properties" />
                <include name="**/*.txt" />
            </fileset>
            <filterset>
                <filter token="APP_NAME" value="${app.name}" />
                <filter token="APP_VERSION" value="${app.version}" />
                <filter token="ENVIRONMENT" value="${environment}" />
                <filter token="API_BASE_URL" value="${api.base.url}" />
            </filterset>
        </copy>
    </target>

    <target name="copy-binary">
        <copy todir="${dist.dir}" overwrite="true">
            <fileset dir="${resources.dir}">
                <include name="**/*.png" />
                <include name="**/*.jpg" />
                <include name="**/*.jpeg" />
                <include name="**/*.gif" />
                <include name="**/*.woff" />
                <include name="**/*.woff2" />
                <include name="**/*.ttf" />
            </fileset>
        </copy>
    </target>

    <target name="prepare-resources" depends="copy-text,copy-binary">
        <echo message="Resources copied to ${dist.dir}" />
    </target>
</project>
```

Chạy:

```bash
ant -Dapp.version=2.0.0 -Denvironment=production -Dapi.base.url=https://api.example.com prepare-resources
```

Tệp `app.properties` và `banner.txt` trong thư mục đích nhận các giá trị thay token. Ảnh và font được sao chép bằng task riêng, không có filterset nên byte nội dung được giữ nguyên.

Kết quả thư mục đích:

```text
build/resources/
├── config/
│   ├── app.properties
│   └── banner.txt
└── static/
    ├── logo.png
    └── fonts/
        └── app.woff2
```

## 11. Bài thực hành

Tạo dự án:

```text
copy-filter-lab/
├── build.xml
└── src/main/resources/
    ├── config/
    │   └── app.properties
    ├── text/
    │   └── welcome.txt
    └── images/
        └── logo.png
```

Nội dung `config/app.properties`:

```properties
app.name=@APP_NAME@
app.version=@APP_VERSION@
```

Nội dung `text/welcome.txt`:

```text
Welcome to @APP_NAME@!
Current release: @APP_VERSION@
```

Hãy viết buildfile để:

1. Khai báo property `app.name`, `app.version` và `build.dir`.
2. Sao chép riêng `.properties` và `.txt` vào `${build.dir}/resources`, thay token `APP_NAME` và `APP_VERSION` bằng FilterSet.
3. Sao chép `.png` vào cùng thư mục đích bằng một task copy riêng, không dùng filterset hoặc filterchain.
4. Tạo target `copy-resources` phụ thuộc vào hai target copy con.
5. Cho phép truyền phiên bản khác từ dòng lệnh bằng `-Dapp.version=...`.
6. Kiểm tra nội dung tệp văn bản sau khi copy và so sánh ảnh nguồn/đích để xác nhận ảnh không bị xử lý như văn bản.

Gợi ý cho nhóm văn bản:

```xml
<copy todir="${build.dir}/resources">
    <fileset dir="src/main/resources">
        <include name="**/*.properties" />
        <include name="**/*.txt" />
    </fileset>
    <filterset>
        <filter token="APP_NAME" value="${app.name}" />
        <filter token="APP_VERSION" value="${app.version}" />
    </filterset>
</copy>
```

Gợi ý cho nhóm nhị phân:

```xml
<copy todir="${build.dir}/resources">
    <fileset dir="src/main/resources">
        <include name="**/*.png" />
    </fileset>
</copy>
```

### Câu hỏi tự kiểm tra

1. `filterset` thay thế token theo quy tắc nào?
2. Khác biệt giữa FilterSet lồng trong task copy và bộ lọc toàn cục được khai báo bằng `<filter>` là gì?
3. `filtering="true"` có tác dụng gì?
4. `filterchain` phù hợp với những phép biến đổi nào?
5. Vì sao cần tách tệp văn bản và nhị phân thành các task copy riêng?
6. Một tệp SVG có nhất thiết là nhị phân chỉ vì nó được dùng làm hình ảnh không?
7. Khi thay token trong XML hoặc JSON, cần chú ý điều gì về giá trị thay thế?
8. Nếu ứng dụng cần giữ nguyên `${DATABASE_URL}`, vì sao không nên áp dụng `expandproperties` cho tệp đó?

### Đáp án gợi ý

- FilterSet thay các token được bao quanh bởi cặp dấu phân cách (mặc định `@`), theo cặp `token` và `value`.
- FilterSet cục bộ áp dụng cho task copy cụ thể; `<filter>` khai báo bộ lọc toàn cục, được dùng khi copy bật `filtering="true"`.
- `filtering="true"` bật việc áp dụng các global filters lên nội dung được copy.
- FilterChain dùng các bộ lọc nội dung như `replacetokens`, `expandproperties` và các filter reader khác.
- Tách riêng giúp chỉ xử lý văn bản bằng bộ lọc, giữ byte của tệp nhị phân nguyên vẹn.
- Không. SVG thường là XML dạng văn bản; chỉ lọc khi thật sự cần thay token trong nội dung.
- Giá trị thay thế phải hợp lệ theo cú pháp XML hoặc JSON, bao gồm escape ký tự đặc biệt.
- `expandproperties` có thể thay placeholder mà ứng dụng cần nhận và xử lý ở thời điểm chạy.

## Kết luận

Task `<copy>` có thể sao chép một tệp hoặc một nhóm resource được chọn bằng FileSet. Với tệp văn bản, FilterSet thay token và FilterChain thực hiện các phép biến đổi nội dung; bộ lọc toàn cục được khai báo bằng `<filter>` và bật qua `filtering="true"`. Hãy phân loại tài nguyên rõ ràng, tách task copy văn bản khỏi task copy nhị phân và chỉ áp dụng bộ lọc cho nhóm tệp thực sự cần thay đổi. Cách tổ chức này giúp cấu hình theo môi trường linh hoạt mà vẫn giữ nguyên dữ liệu ảnh, font, archive, PDF và các tệp nhị phân khác.
