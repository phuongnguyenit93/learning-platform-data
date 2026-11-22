# `FilterSet`, `FilterChain` và dữ liệu cấu hình cho xử lý nội dung

Trong một dự án Java, nhiều tệp tài nguyên cần được đưa từ thư mục nguồn sang thư mục build: tệp `.properties`, XML, HTML, CSS, JavaScript, mẫu cấu hình hoặc tài liệu triển khai. Một số tệp chứa các giá trị thay đổi theo môi trường như tên ứng dụng, URL dịch vụ, phiên bản hoặc thư mục triển khai. Thay vì sửa trực tiếp từng tệp nguồn cho mỗi môi trường, Apache Ant có thể xử lý nội dung khi sao chép.

Ant cung cấp hai cơ chế thường dùng cho công việc này là `FilterSet` và `FilterChain`. `FilterSet` thay thế token theo cặp khóa/giá trị. `FilterChain` đưa nội dung qua một chuỗi bộ lọc văn bản, có thể thay token, mở rộng property hoặc biến đổi từng dòng. Chọn đúng cơ chế giúp dữ liệu cấu hình được đưa vào tài nguyên đầu ra theo cách có thể lặp lại và dễ kiểm soát.

## 1. Vì sao cần lọc nội dung khi build?

Giả sử dự án có một tệp mẫu cấu hình:

```properties
application.name=@app.name@
application.version=@app.version@
service.url=@service.url@
```

Các giá trị trong dấu `@...@` là token chờ được thay thế. Khi build cho môi trường kiểm thử, dự án có thể cần URL của máy chủ kiểm thử; khi build cho môi trường production, URL cần thay đổi. Nếu chỉnh sửa trực tiếp tệp nguồn mỗi lần build, rất dễ đưa nhầm cấu hình của môi trường này sang môi trường khác hoặc làm mất nội dung mẫu ban đầu.

Một cách tốt hơn là giữ tệp mẫu trong thư mục nguồn, lưu dữ liệu cấu hình ở một tệp riêng và yêu cầu Ant tạo bản đã xử lý trong thư mục đầu ra:

```text
project/
├── build.xml
├── config/
│   ├── test.properties
│   └── production.properties
├── src/
│   └── main/resources/
│       └── application.properties
└── build/
    └── resources/
        └── application.properties
```

Tệp trong `src` tiếp tục là mẫu nguồn; tệp trong `build` là kết quả được tạo cho lần build cụ thể.

## 2. `FilterSet`: thay thế token theo cặp khóa và giá trị

`FilterSet` là một nhóm bộ lọc token. Mỗi bộ lọc xác định một token và giá trị thay thế. Khi task hỗ trợ filterset sao chép nội dung, Ant tìm token trong văn bản và thay token bằng giá trị tương ứng.

Ví dụ đơn giản:

```xml
<copy file="src/main/resources/application.properties"
      tofile="build/resources/application.properties">
    <filterset begintoken="@" endtoken="@">
        <filter token="app.name" value="Inventory Service"/>
        <filter token="app.version" value="1.4.0"/>
        <filter token="service.url" value="https://test.example.internal"/>
    </filterset>
</copy>
```

Với tệp nguồn:

```properties
application.name=@app.name@
application.version=@app.version@
service.url=@service.url@
```

nội dung đầu ra sẽ tương ứng với các giá trị được khai báo trong filterset:

```properties
application.name=Inventory Service
application.version=1.4.0
service.url=https://test.example.internal
```

Các thành phần quan trọng:

- `begintoken` xác định chuỗi bắt đầu token; ví dụ `@`.
- `endtoken` xác định chuỗi kết thúc token; ví dụ `@`.
- `<filter token="..." value="..."/>` khai báo tên token và giá trị thay thế.
- `<copy>` thực hiện sao chép và áp dụng filterset trong quá trình xử lý nội dung.

Token trong tệp nguồn phải khớp chính xác với tên token và cặp dấu phân cách. Với `begintoken="@"` và `endtoken="@"`, token `@app.name@` được ánh xạ tới filter có `token="app.name"`.

## 3. Lưu dữ liệu token trong tệp cấu hình riêng

Khi có nhiều token hoặc nhiều môi trường, đặt giá trị trực tiếp trong `build.xml` sẽ khiến buildfile dài và khó quản lý. Có thể lưu các cặp khóa/giá trị trong một tệp properties:

`config/test.properties`:

```properties
app.name=Inventory Service
app.version=1.4.0
service.url=https://test.example.internal
```

`config/production.properties`:

```properties
app.name=Inventory Service
app.version=1.4.0
service.url=https://api.example.com
```

Sau đó, dùng thuộc tính `filtersfile` của filterset để đọc dữ liệu:

```xml
<project name="inventory-service" default="copy-test-resources" basedir=".">

    <property name="config.file" location="config/test.properties"/>
    <property name="source.resources" location="src/main/resources"/>
    <property name="output.resources" location="build/resources"/>

    <target name="copy-test-resources">
        <mkdir dir="${output.resources}"/>
        <copy todir="${output.resources}">
            <fileset dir="${source.resources}"/>
            <filterset filtersfile="${config.file}"
                       begintoken="@" endtoken="@"/>
        </copy>
    </target>

</project>
```

Tệp `filtersfile` dùng định dạng properties: mỗi dòng biểu diễn một cặp tên token và giá trị. Ví dụ `app.name=Inventory Service` cung cấp giá trị cho token `@app.name@` trong nội dung nguồn.

Khi đổi môi trường, có thể thay property `config.file` để đọc tệp cấu hình tương ứng. Cũng có thể nhận đường dẫn cấu hình từ dòng lệnh bằng property của Ant, ví dụ:

```sh
ant -Dconfig.file=config/production.properties copy-test-resources
```

Để lệnh trên có hiệu lực, buildfile cần tham chiếu `${config.file}` trong `filtersfile` và khai báo giá trị mặc định theo cách cho phép property dòng lệnh ghi đè. Ant property là bất biến; nếu `config.file` được đặt cứng trước bằng `<property>`, giá trị truyền bằng `-D` vẫn có ưu tiên cao hơn property trong buildfile. Có thể đặt giá trị mặc định bằng `<property name="config.file" location="config/test.properties"/>` rồi ghi đè khi gọi Ant.

## 4. `FilterChain`: xử lý nội dung qua nhiều bộ lọc

`FilterChain` là một chuỗi các filter reader. Thay vì chỉ ánh xạ token sang giá trị như filterset, nó cho phép kết hợp nhiều bước xử lý văn bản. Ví dụ, có thể mở rộng Ant property trong nội dung, thay token, lọc dòng hoặc biến đổi văn bản trước khi ghi ra đích.

Một ví dụ dùng `expandproperties` và `replacetokens`:

```xml
<project name="filter-chain-demo" default="copy-resources" basedir=".">

    <property name="app.name" value="Inventory Service"/>
    <property name="app.version" value="1.4.0"/>

    <target name="copy-resources">
        <mkdir dir="build/resources"/>
        <copy todir="build/resources">
            <fileset dir="src/main/resources"/>
            <filterchain>
                <expandproperties/>
                <replacetokens begintoken="@" endtoken="@">
                    <token key="APP_NAME" value="${app.name}"/>
                    <token key="APP_VERSION" value="${app.version}"/>
                </replacetokens>
            </filterchain>
        </copy>
    </target>

</project>
```

Tệp mẫu có thể chứa cả Ant property và token riêng:

```properties
application.name=@APP_NAME@
application.version=@APP_VERSION@
build.label=${app.name}-${app.version}
```

`<expandproperties/>` mở rộng biểu thức `${...}` dựa trên các property Ant đang có. `<replacetokens>` thay các token theo `key` và `value`. Vì các filter trong chain được áp dụng theo thứ tự khai báo, hãy sắp xếp chúng sao cho đầu ra của bước trước phù hợp với đầu vào của bước tiếp theo.

Trong ví dụ này, kết quả cuối cùng là văn bản đã được mở rộng property và thay token. Các filter reader có thể được kết hợp để xử lý nội dung theo một quy trình, thay vì phải tạo nhiều tệp trung gian cho từng bước.

## 5. Một số filter reader thường dùng trong `FilterChain`

Ant cung cấp nhiều filter reader tích hợp. Tùy nhu cầu, có thể chọn một hoặc kết hợp nhiều filter trong `<filterchain>`.

| Filter | Mục đích |
|---|---|
| `expandproperties` | Mở rộng các biểu thức property Ant dạng `${property.name}` trong nội dung |
| `replacetokens` | Thay token theo cặp key/value và ký hiệu phân cách |
| `linecontains` | Chỉ giữ những dòng chứa một chuỗi được chỉ định |
| `linecontainsregexp` | Lọc dòng dựa trên biểu thức chính quy |
| `headfilter` | Giữ một số dòng đầu của nội dung |
| `tailfilter` | Giữ một số dòng cuối của nội dung |
| `prefixlines` | Thêm tiền tố vào từng dòng |
| `tabstospaces` | Chuyển ký tự tab thành khoảng trắng |
| `striplinebreaks` | Loại bỏ ký tự xuống dòng |
| `striplinecomments` | Loại bỏ phần chú thích theo quy tắc comment được cấu hình |
| `replaceregexp` | Thay thế phần văn bản khớp biểu thức chính quy |

Ví dụ lọc các dòng chứa từ `enabled`:

```xml
<copy file="src/config/features.txt" tofile="build/features.txt">
    <filterchain>
        <linecontains>
            <contains value="enabled"/>
        </linecontains>
    </filterchain>
</copy>
```

Nếu tệp nguồn là:

```text
feature.login=enabled
feature.payment=disabled
feature.search=enabled
```

đầu ra chỉ giữ các dòng chứa chuỗi `enabled`:

```text
feature.login=enabled
feature.search=enabled
```

Filter reader làm thay đổi luồng văn bản, vì vậy hãy kiểm tra kỹ kết quả nếu dùng chúng để xử lý tệp cấu hình có định dạng chặt chẽ.

## 6. So sánh `FilterSet` và `FilterChain`

Hai cơ chế có thể cùng tham gia xử lý nội dung trong các task hỗ trợ, nhưng giải quyết nhu cầu khác nhau.

| Tiêu chí | `FilterSet` | `FilterChain` |
|---|---|---|
| Mục tiêu chính | Thay token theo cặp token/giá trị | Xử lý văn bản qua một chuỗi filter reader |
| Cách khai báo | `<filterset>` với `<filter>` hoặc `filtersfile` | `<filterchain>` với các filter reader con |
| Dữ liệu đầu vào | Nội dung chứa token được đánh dấu | Luồng văn bản cần biến đổi/lọc |
| Khả năng | Thay token với delimiter cấu hình | Mở rộng property, thay token, lọc dòng và biến đổi nội dung |
| Trường hợp điển hình | Điền giá trị cấu hình vào tệp mẫu | Kết hợp nhiều bước xử lý nội dung |

Chọn `FilterSet` khi yêu cầu chủ yếu là thay các placeholder rõ ràng như `@service.url@`. Chọn `FilterChain` khi cần một pipeline xử lý văn bản với nhiều bước, ví dụ mở rộng property rồi thay token hoặc lọc dòng.

Không nên dùng filter chỉ vì task cho phép. Nếu tệp cần được sao chép nguyên trạng, hãy sao chép mà không bật xử lý nội dung. Việc lọc không cần thiết có thể làm thay đổi dữ liệu ngoài ý muốn.

## 7. Kết hợp dữ liệu cấu hình với nhiều môi trường

Một buildfile có thể nhận profile từ dòng lệnh và chọn tệp cấu hình tương ứng. Ví dụ:

```xml
<project name="environment-build" default="copy-resources" basedir=".">

    <property name="profile" value="test"/>
    <property name="config.file" location="config/${profile}.properties"/>

    <target name="copy-resources">
        <mkdir dir="build/${profile}/resources"/>
        <copy todir="build/${profile}/resources">
            <fileset dir="src/main/resources"/>
            <filterset filtersfile="${config.file}"
                       begintoken="@" endtoken="@"/>
        </copy>
    </target>

</project>
```

Build mặc định dùng profile `test`:

```sh
ant copy-resources
```

Để dùng profile `production`:

```sh
ant -Dprofile=production copy-resources
```

Do Ant property bất biến, property truyền từ dòng lệnh bằng `-D` được thiết lập trước các property khai báo trong buildfile. Vì vậy, giá trị mặc định `test` chỉ được dùng khi người gọi không truyền `profile`.

Tệp cấu hình cần tồn tại tại đường dẫn được tạo từ profile. Nếu chọn một profile không có tệp tương ứng, Ant có thể báo lỗi khi filterset đọc `filtersfile`. Hãy xác định rõ cách xử lý khi thiếu file cấu hình; không nên âm thầm build bằng cấu hình của môi trường khác.

## 8. Encoding và giới hạn khi lọc tệp

FilterSet và FilterChain xử lý nội dung văn bản. Chúng phù hợp với tệp cấu hình, XML, HTML, CSS, JavaScript hoặc các mẫu văn bản khác. Không dùng chúng để lọc tệp nhị phân như ảnh, font, JAR, ZIP hoặc dữ liệu đã mã hóa, vì việc chuyển đổi ký tự có thể làm hỏng nội dung.

Khi xử lý văn bản có dấu hoặc ký tự ngoài ASCII, encoding của tệp nguồn và tệp đích cần được xác định phù hợp. Với các phiên bản Ant và task hỗ trợ, có thể cấu hình `encoding` và `outputencoding` trên task sao chép để chỉ rõ charset đọc và ghi. Ví dụ:

```xml
<copy todir="build/resources" encoding="UTF-8" outputencoding="UTF-8">
    <fileset dir="src/main/resources" includes="**/*.properties"/>
    <filterset begintoken="@" endtoken="@">
        <filter token="app.name" value="Dịch vụ quản lý"/>
    </filterset>
</copy>
```

Hãy kiểm tra phiên bản Ant đang dùng và task cụ thể có hỗ trợ các thuộc tính encoding này hay không. Nếu nguồn và đích dùng charset khác nhau, khai báo không chính xác có thể gây lỗi ký tự hoặc tạo nội dung bị sai dấu.

Một số lưu ý khác:

- Chỉ áp dụng filter cho nhóm tệp cần thay đổi, chẳng hạn `**/*.properties` hoặc `**/*.xml`.
- Không bật filtering trên toàn bộ thư mục nếu trong đó có ảnh, font hoặc tệp nhị phân.
- Token trong mẫu nên có delimiter đủ đặc trưng để tránh thay nhầm văn bản thông thường.
- Giá trị cấu hình có ký tự đặc biệt cần được kiểm tra trong định dạng đích. Filter thay chuỗi không tự escape giá trị thành cú pháp XML, JSON, URL hoặc JavaScript an toàn.
- Nếu token không có giá trị tương ứng, cần kiểm tra đầu ra để tránh placeholder còn sót lại.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Token vẫn còn trong tệp đầu ra | Tên token hoặc delimiter không khớp, hoặc filterset/filterchain không được áp dụng cho task | So sánh token trong tệp mẫu với `token`, `begintoken` và `endtoken`; kiểm tra filter được lồng đúng task |
| Tệp cấu hình không được tìm thấy | Đường dẫn `filtersfile` sai hoặc profile tạo ra tên tệp không tồn tại | In `${config.file}`, kiểm tra file và thư mục cấu hình |
| Giá trị không thay đổi dù đã khai báo filter | Một property hoặc token được tham chiếu sai cú pháp | Phân biệt `@token@`, `${property}` và `@{macroAttribute}`; dùng cú pháp phù hợp với cơ chế |
| Kết quả có ký tự tiếng Việt bị lỗi | Charset đọc/ghi không phù hợp với tệp nguồn hoặc đích | Xác định encoding của tệp và cấu hình encoding được task hỗ trợ |
| Tệp ảnh hoặc ZIP bị hỏng sau copy | Đã áp dụng filter văn bản lên dữ liệu nhị phân | Loại tệp nhị phân khỏi fileset được lọc; sao chép chúng nguyên trạng |
| Dữ liệu bị thay đổi ngoài dự kiến | FilterChain có nhiều bước hoặc filter áp dụng cho quá nhiều tệp | Thu hẹp fileset, kiểm tra thứ tự filter và so sánh đầu ra với tệp mẫu |
| Token vẫn sót khi thiếu khóa cấu hình | Tệp filter không định nghĩa token tương ứng | Bổ sung khóa bắt buộc và kiểm tra cấu hình trước khi đóng gói |

## 10. Quy trình mẫu cho tài nguyên cấu hình

Một quy trình dễ quản lý thường gồm các bước:

1. Lưu tệp mẫu có token trong `src/main/resources`.
2. Lưu các cặp token/giá trị trong tệp properties theo môi trường.
3. Chọn profile bằng property mặc định hoặc tham số `-D`.
4. Tạo thư mục đầu ra bằng `<mkdir>`.
5. Dùng `<copy>` kết hợp `FilterSet` hoặc `FilterChain` để xử lý nội dung.
6. Kiểm tra tệp kết quả trong thư mục build trước khi đóng gói.

Ví dụ kiểm tra đầu ra bằng task `echo` và task copy:

```xml
<project name="resource-processing" default="prepare-resources" basedir=".">

    <property name="profile" value="test"/>
    <property name="config.file" location="config/${profile}.properties"/>
    <property name="output.dir" location="build/${profile}/resources"/>

    <target name="prepare-resources">
        <mkdir dir="${output.dir}"/>
        <copy todir="${output.dir}" encoding="UTF-8" outputencoding="UTF-8">
            <fileset dir="src/main/resources" includes="**/*.properties"/>
            <filterset filtersfile="${config.file}"
                       begintoken="@" endtoken="@"/>
        </copy>
        <echo message="Processed resources for profile ${profile}: ${output.dir}"/>
    </target>

</project>
```

Chạy cho môi trường kiểm thử:

```sh
ant prepare-resources
```

Chạy cho môi trường production:

```sh
ant -Dprofile=production prepare-resources
```

Sau mỗi lần chạy, kiểm tra nội dung trong `build/test/resources` hoặc `build/production/resources`. Các tệp nguồn không bị thay đổi bởi bước xử lý này.

## 11. Checklist sử dụng `FilterSet` và `FilterChain`

- [ ] Đã xác định nội dung cần thay token hay cần nhiều bước biến đổi văn bản.
- [ ] Token trong mẫu khớp với delimiter và tên token được khai báo.
- [ ] Dữ liệu cấu hình được lưu riêng và chọn đúng theo profile.
- [ ] `filtersfile` trỏ tới tệp có thật và chứa các cặp khóa/giá trị cần thiết.
- [ ] FilterChain được sắp xếp theo thứ tự xử lý mong muốn.
- [ ] Chỉ áp dụng filtering cho tệp văn bản cần xử lý.
- [ ] Encoding nguồn và đích được xác định phù hợp khi task hỗ trợ.
- [ ] Đã kiểm tra đầu ra để phát hiện token còn sót, ký tự lỗi hoặc dữ liệu bị thay đổi ngoài dự kiến.
- [ ] Tệp mẫu trong thư mục nguồn vẫn giữ nguyên sau build.

`FilterSet` phù hợp với việc điền token từ dữ liệu cấu hình; `FilterChain` phù hợp với một quy trình xử lý văn bản gồm nhiều filter reader. Khi tổ chức dữ liệu cấu hình riêng theo môi trường và chỉ lọc những tệp cần thiết, Ant có thể tạo tài nguyên đầu ra nhất quán mà không phải chỉnh sửa mẫu nguồn thủ công.
