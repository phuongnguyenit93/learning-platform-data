# Nạp mẫu và tạo tệp cấu hình cho từng môi trường

## Mục tiêu

Trong một dự án, các môi trường phát triển, kiểm thử và vận hành thường dùng chung cấu trúc cấu hình nhưng khác nhau ở một số giá trị như tên ứng dụng, cổng dịch vụ, URL cơ sở dữ liệu, thư mục log hoặc mức ghi log. Nếu duy trì một tệp cấu hình riêng hoàn toàn cho mỗi môi trường, các thay đổi về cấu trúc dễ bị lệch nhau và khó kiểm soát.

Apache Ant có thể tạo tệp cấu hình từ một mẫu văn bản bằng cách nạp các giá trị theo môi trường rồi thay thế những vị trí đánh dấu trong mẫu. Cách làm này thường gồm các bước:

1. Chuẩn bị một tệp mẫu chứa các token cần thay thế.
2. Lưu giá trị riêng của từng môi trường trong các tệp properties.
3. Nạp tệp properties tương ứng khi chạy build.
4. Dùng FilterSet hoặc FilterChain để thay thế token trong mẫu.
5. Ghi kết quả thành tệp cấu hình riêng cho môi trường đó.

Ant cung cấp hai cơ chế thường dùng:

- **FilterSet** thay thế token theo cặp dấu phân cách, mặc định là `@TOKEN@`.
- **FilterChain với ExpandProperties** thay thế biểu thức property theo cú pháp `${property.name}`.

Hai cách có thể phục vụ cùng mục đích, nhưng cú pháp trong mẫu và nơi lưu giá trị khác nhau. Chọn một quy ước nhất quán giúp mẫu dễ đọc, dễ kiểm tra và không vô tình thay thế các chuỗi không liên quan.

## 1. Tổ chức mẫu và tệp cấu hình theo môi trường

Một cấu trúc thư mục dễ quản lý có thể như sau:

~~~text
project/
├── build.xml
├── config/
│   ├── dev.properties
│   ├── test.properties
│   └── prod.properties
├── templates/
│   └── application.properties.template
└── build/
    └── config/
        ├── dev/
        ├── test/
        └── prod/
~~~

Trong đó:

- `templates/application.properties.template` là mẫu dùng chung.
- `config/dev.properties`, `config/test.properties` và `config/prod.properties` chứa giá trị riêng của từng môi trường.
- `build/config/<env>/application.properties` là tệp đầu ra được Ant tạo ra.

Mẫu có thể chứa những token như:

~~~properties
application.name=@APP_NAME@
server.port=@SERVER_PORT@
database.url=@DATABASE_URL@
logging.level=@LOG_LEVEL@
~~~

Các giá trị cụ thể được lưu theo môi trường. Ví dụ:

**config/dev.properties**

~~~properties
app.name=Sample App - Development
server.port=8081
database.url=jdbc:postgresql://localhost:5432/sample_dev
log.level=DEBUG
~~~

**config/test.properties**

~~~properties
app.name=Sample App - Test
server.port=8181
database.url=jdbc:postgresql://test-db.internal:5432/sample_test
log.level=INFO
~~~

**config/prod.properties**

~~~properties
app.name=Sample App
server.port=8080
database.url=jdbc:postgresql://prod-db.internal:5432/sample
log.level=WARN
~~~

Tên key trong các tệp properties là quy ước của dự án. Khi dùng FilterSet, ta có thể ánh xạ các key này sang token trong mẫu. Khi dùng ExpandProperties, tên property trong mẫu cần trùng với tên property Ant đã nạp.

## 2. Cách thứ nhất: dùng FilterSet để thay token

### 2.1. Token mặc định

FilterSet thay thế các đoạn văn bản nằm giữa hai dấu phân cách. Mặc định, dấu bắt đầu và kết thúc là ký tự `@`.

Ví dụ, token:

~~~text
@APP_NAME@
~~~

sẽ được thay bằng giá trị được khai báo cho token `APP_NAME`.

Có thể khai báo trực tiếp các cặp token và giá trị bằng phần tử `filter`:

~~~xml
<copy file="templates/application.properties.template"
      tofile="build/application.properties">
    <filterset>
        <filter token="APP_NAME" value="Sample App"/>
        <filter token="SERVER_PORT" value="8080"/>
    </filterset>
</copy>
~~~

Khi target chạy, Ant đọc tệp mẫu và thay token tương ứng trong nội dung đầu ra. Phần văn bản không khớp token được giữ nguyên.

### 2.2. Nạp token từ filtersfile

Nếu mỗi môi trường có nhiều giá trị, không nên viết tất cả token trực tiếp trong buildfile. Có thể dùng phần tử `filtersfile` bên trong FilterSet:

~~~xml
<copy file="templates/application.properties.template"
      tofile="build/application.properties">
    <filterset>
        <filtersfile file="config/filters.properties"/>
    </filterset>
</copy>
~~~

Tệp filters có dạng cặp key-value:

~~~properties
APP_NAME=Sample App
SERVER_PORT=8080
DATABASE_URL=jdbc:postgresql://localhost:5432/sample
LOG_LEVEL=INFO
~~~

FilterSet sử dụng key làm token và value làm nội dung thay thế. Với dấu phân cách mặc định, key `APP_NAME` thay cho chuỗi `@APP_NAME@`.

Cần phân biệt hai cách nạp dữ liệu:

- Phần tử `<property file="..."/>` nạp key-value vào hệ thống Ant property, để dùng với cú pháp `${...}`.
- Phần tử `<filtersfile file="..."/>` nạp key-value vào FilterSet, để dùng với token như `@APP_NAME@`.

Dù định dạng tệp đều có dạng key-value, hai cơ chế có mục đích và phạm vi thay thế khác nhau.

### 2.3. Đổi dấu phân cách token

Nếu mẫu đã dùng ký tự `@` cho mục đích khác, có thể chọn dấu phân cách riêng bằng thuộc tính `begintoken` và `endtoken`:

~~~xml
<copy file="templates/application.properties.template"
      tofile="build/application.properties">
    <filterset begintoken="%%" endtoken="%%">
        <filter token="APP_NAME" value="Sample App"/>
    </filterset>
</copy>
~~~

Mẫu tương ứng sẽ dùng:

~~~properties
application.name=%%APP_NAME%%
~~~

Cả dấu bắt đầu và dấu kết thúc phải khớp với cách viết trong mẫu. Nếu cấu hình build dùng `%%` nhưng mẫu vẫn dùng `@APP_NAME@`, token sẽ không được thay thế.

### 2.4. Một FilterSet có nhiều filter

Có thể khai báo nhiều token trong cùng FilterSet:

~~~xml
<filterset>
    <filter token="APP_NAME" value="Sample App"/>
    <filter token="SERVER_PORT" value="8080"/>
    <filter token="DATABASE_URL" value="jdbc:postgresql://localhost:5432/sample"/>
    <filter token="LOG_LEVEL" value="INFO"/>
</filterset>
~~~

Mỗi token được thay thế theo giá trị tương ứng. Nếu một token không có filter tương ứng, chuỗi token đó thường được giữ nguyên. Vì vậy, khi đầu ra còn chứa `@DATABASE_URL@`, hãy kiểm tra tên token, filtersfile và giá trị đã được nạp.

### 2.5. Dùng nhiều FilterSet

Có thể khai báo nhiều FilterSet lồng trong task copy, chẳng hạn khi một nhóm token dùng chung và nhóm khác chỉ dành cho một tệp. Tuy nhiên, nếu nhiều FilterSet cùng định nghĩa một token, thứ tự áp dụng có thể ảnh hưởng kết quả. Hãy tránh định nghĩa trùng token nếu không có chủ đích rõ ràng.

Với cấu hình theo môi trường, thường dễ bảo trì hơn khi mỗi lần tạo đầu ra sử dụng một filtersfile hoặc một FilterSet xác định duy nhất.

## 3. Tạo tệp cấu hình theo môi trường bằng FilterSet

Giả sử mỗi môi trường có một filtersfile riêng:

~~~text
config/
├── filters/
│   ├── dev.properties
│   ├── test.properties
│   └── prod.properties
~~~

Ví dụ nội dung `config/filters/dev.properties`:

~~~properties
APP_NAME=Sample App - Development
SERVER_PORT=8081
DATABASE_URL=jdbc:postgresql://localhost:5432/sample_dev
LOG_LEVEL=DEBUG
~~~

Tệp test và prod có cùng key nhưng giá trị khác nhau.

Buildfile có thể nhận tên môi trường qua property `env`:

~~~xml
<project name="environment-config" default="generate" basedir=".">
    <property name="template.file" location="templates/application.properties.template"/>
    <property name="config.dir" location="config/filters"/>
    <property name="output.root" location="build/config"/>

    <target name="validate">
        <fail unless="env"
              message="Hay truyen -Denv=dev, -Denv=test hoac -Denv=prod."/>

        <available file="${config.dir}/${env}.properties"
                   property="env.filters.exists"/>

        <fail unless="env.filters.exists"
              message="Khong tim thay filtersfile cho moi truong da chon."/>
    </target>

    <target name="generate" depends="validate">
        <mkdir dir="${output.root}/${env}"/>

        <copy file="${template.file}"
              tofile="${output.root}/${env}/application.properties"
              overwrite="true">
            <filterset>
                <filtersfile file="${config.dir}/${env}.properties"/>
            </filterset>
        </copy>
    </target>
</project>
~~~

Chạy cho môi trường phát triển:

~~~text
ant -Denv=dev generate
~~~

Chạy cho môi trường kiểm thử:

~~~text
ant -Denv=test generate
~~~

Chạy cho môi trường vận hành:

~~~text
ant -Denv=prod generate
~~~

Mỗi lần chạy tạo tệp đầu ra trong thư mục riêng:

~~~text
build/config/dev/application.properties
build/config/test/application.properties
build/config/prod/application.properties
~~~

Thuộc tính `overwrite="true"` yêu cầu copy ghi lại đầu ra ngay cả khi tệp đích đã tồn tại và mẫu nguồn không mới hơn tệp đích. Điều này hữu ích khi giá trị trong filtersfile thay đổi nhưng thời gian sửa đổi của mẫu không thay đổi.

Các target validate giúp phát hiện sớm trường hợp chưa truyền `env` hoặc không có filtersfile tương ứng. Tên môi trường được truyền từ dòng lệnh nên phải khớp tên tệp trong thư mục filters.

## 4. Cách thứ hai: nạp property file và dùng ExpandProperties

FilterSet phù hợp với token dạng `@TOKEN@`. Một lựa chọn khác là viết mẫu theo cú pháp property của Ant:

~~~properties
application.name=${app.name}
server.port=${server.port}
database.url=${database.url}
logging.level=${log.level}
~~~

Sau đó, nạp tệp property của môi trường và dùng FilterChain với ExpandProperties để thay thế biểu thức.

### 4.1. Nạp property file

Task `property` có thể đọc tệp properties:

~~~xml
<property file="config/dev.properties"/>
~~~

Với tệp:

~~~properties
app.name=Sample App - Development
server.port=8081
database.url=jdbc:postgresql://localhost:5432/sample_dev
log.level=DEBUG
~~~

Ant tạo các property tương ứng để dùng trong buildfile và các bộ lọc có hỗ trợ property expansion.

### 4.2. Dùng ExpandProperties

Trong task copy, khai báo FilterChain chứa ExpandProperties:

~~~xml
<copy file="templates/application.properties.template"
      tofile="build/application.properties"
      overwrite="true">
    <filterchain>
        <expandproperties/>
    </filterchain>
</copy>
~~~

ExpandProperties đọc nội dung văn bản và thay các biểu thức property có giá trị trong Ant. Ví dụ `${app.name}` được thay bằng giá trị của property `app.name`.

Phần mẫu không có biểu thức property phù hợp được giữ lại theo nội dung ban đầu. Vì vậy, nếu kết quả còn `${server.port}`, hãy kiểm tra property đã được nạp chưa và tên có chính xác không.

### 4.3. Buildfile hoàn chỉnh cho một môi trường

Có thể viết target nhận `env`, nạp tệp tương ứng rồi xử lý mẫu:

~~~xml
<project name="expand-properties-config" default="generate" basedir=".">
    <property name="config.dir" location="config"/>
    <property name="template.file" location="templates/application.properties.template"/>
    <property name="output.root" location="build/config"/>

    <target name="validate">
        <fail unless="env"
              message="Hay truyen -Denv=dev, -Denv=test hoac -Denv=prod."/>

        <available file="${config.dir}/${env}.properties"
                   property="env.config.exists"/>

        <fail unless="env.config.exists"
              message="Khong tim thay property file cho moi truong da chon."/>
    </target>

    <target name="generate" depends="validate">
        <property file="${config.dir}/${env}.properties"/>

        <mkdir dir="${output.root}/${env}"/>

        <copy file="${template.file}"
              tofile="${output.root}/${env}/application.properties"
              overwrite="true">
            <filterchain>
                <expandproperties/>
            </filterchain>
        </copy>
    </target>
</project>
~~~

Chạy:

~~~text
ant -Denv=dev generate
~~~

Ant đọc `config/dev.properties`, sau đó ExpandProperties thay các biểu thức trong mẫu và ghi tệp cấu hình vào `build/config/dev/application.properties`.

### 4.4. Property của Ant và property trong ứng dụng

Cần phân biệt property dùng để điều khiển build với property sẽ xuất hiện trong tệp cấu hình của ứng dụng.

Ví dụ, nếu mẫu chứa:

~~~properties
database.url=${database.url}
~~~

ExpandProperties sẽ tìm property `database.url` trong Ant. Nếu đã nạp property đó từ tệp môi trường, nó sẽ được thay bằng giá trị. Nếu chưa nạp, biểu thức có thể còn nguyên trong đầu ra.

Nếu ứng dụng cũng dùng cú pháp `${...}` để tự đọc cấu hình khi chạy, không nên áp dụng ExpandProperties lên những biểu thức cần giữ lại cho ứng dụng. Trong trường hợp đó, dùng token riêng như `@DATABASE_URL@` với FilterSet sẽ rõ ràng hơn.

## 5. Chọn FilterSet hay ExpandProperties?

| Tiêu chí | FilterSet | ExpandProperties |
|---|---|---|
| Cú pháp trong mẫu | `@APP_NAME@` | `${app.name}` |
| Nguồn giá trị | filter trực tiếp hoặc filtersfile | Ant properties |
| Phạm vi thay thế | Token khớp dấu phân cách | Biểu thức property Ant |
| Dễ phân biệt với property runtime của ứng dụng | Có, nếu ứng dụng không dùng cùng token | Khó hơn nếu ứng dụng cũng dùng `${...}` |
| Thích hợp khi | Mẫu có placeholder riêng cho build | Mẫu chủ động dùng cú pháp Ant property |

Có thể kết hợp FilterSet và FilterChain trong cùng một quy trình nếu có nhu cầu rõ ràng, nhưng nên giới hạn số quy ước placeholder. Khi mẫu có cả `@TOKEN@` và `${property}`, hãy ghi rõ token nào thuộc build và token nào cần được giữ lại cho ứng dụng.

## 6. Giới hạn quan trọng: Ant property chỉ thiết lập một lần

Property trong Ant có tính chất bất biến. Sau khi một property đã được thiết lập, việc nạp một tệp properties khác với cùng key trong cùng project thường không ghi đè giá trị trước đó.

Ví dụ sau không tạo ra hai cấu hình độc lập như mong muốn:

~~~xml
<property file="config/dev.properties"/>
<copy file="templates/application.properties.template"
      tofile="build/dev/application.properties">
    <filterchain>
        <expandproperties/>
    </filterchain>
</copy>

<property file="config/test.properties"/>
<copy file="templates/application.properties.template"
      tofile="build/test/application.properties">
    <filterchain>
        <expandproperties/>
    </filterchain>
</copy>
~~~

Nếu `dev.properties` đã đặt `database.url`, việc nạp `test.properties` sau đó không thay giá trị đã có. Tệp test có thể vô tình nhận giá trị của dev.

Có ba cách tổ chức an toàn:

1. Chạy Ant thành một tiến trình riêng cho từng môi trường, truyền `-Denv=dev`, `-Denv=test` hoặc `-Denv=prod`. Đây là cách đơn giản và dễ dự đoán.
2. Dùng các key có tiền tố riêng như `dev.database.url`, `test.database.url`, `prod.database.url`, rồi ánh xạ đúng nhóm key vào token.
3. Tách phần sinh cấu hình vào các project con độc lập, mỗi project nạp một bộ property riêng.

Đối với quy trình build thông thường, chạy riêng từng môi trường giúp tránh việc property của lần trước ảnh hưởng lần sau.

## 7. Tạo nhiều cấu hình trong một lần điều phối

Nếu cần một lệnh điều phối tạo cả ba môi trường, có thể để script hoặc CI gọi Ant ba lần, mỗi lần trong một tiến trình mới:

~~~text
ant -Denv=dev generate
ant -Denv=test generate
ant -Denv=prod generate
~~~

Mỗi tiến trình có hệ thống property riêng, vì vậy property của dev không tồn tại để chặn giá trị của test hoặc prod.

Một cách khác là tạo ba buildfile con, mỗi file nạp một bộ property riêng rồi gọi logic tạo cấu hình chung. Cách này có thể hữu ích với dự án lớn, nhưng cần giữ rõ ràng ranh giới giữa project và property được kế thừa.

Không nên cố nạp tuần tự nhiều file môi trường vào cùng một project rồi mong property trùng tên ghi đè nhau. Quy tắc bất biến của Ant khiến cách đó không đáng tin cậy.

## 8. Các lỗi thường gặp khi thay token

### 8.1. Token còn nguyên trong đầu ra

Ví dụ tệp đầu ra vẫn có:

~~~properties
database.url=@DATABASE_URL@
~~~

Nguyên nhân có thể là:

- Tên token trong mẫu khác tên key trong filtersfile.
- Filtersfile không được tìm thấy hoặc không được khai báo đúng.
- Dấu bắt đầu hoặc kết thúc token không khớp.
- FilterSet không được đặt trong task đang sao chép mẫu.

Hãy so sánh chính xác tên token, key và dấu phân cách.

### 8.2. Property còn nguyên trong đầu ra

Nếu mẫu dùng `${database.url}` nhưng kết quả vẫn giữ nguyên biểu thức, hãy kiểm tra:

- Tệp môi trường có chứa key `database.url` không.
- Task property đã nạp đúng tệp trước khi copy chưa.
- Có viết sai tên property hoặc nhầm chữ hoa/chữ thường không.
- Có đang dùng FilterSet trong khi mẫu lại cần ExpandProperties không.

### 8.3. Đầu ra của môi trường này chứa giá trị môi trường khác

Đây thường là hệ quả của việc nạp nhiều tệp vào cùng một Ant project. Do property không ghi đè, lần nạp sau không thay các giá trị đã được thiết lập.

Tách mỗi môi trường thành một lần chạy Ant độc lập hoặc dùng key có tiền tố riêng.

### 8.4. Tệp đích không được cập nhật

Copy có thể bỏ qua tệp đích nếu nó được xem là mới hơn nguồn. Khi giá trị filter thay đổi nhưng tệp mẫu không thay đổi, thời gian sửa đổi của mẫu không đủ để phản ánh thay đổi nội dung đầu ra.

Dùng `overwrite="true"` khi cần tái tạo đầu ra từ các giá trị filter hiện tại.

### 8.5. Nội dung không phải văn bản bị thay đổi

FilterSet và ExpandProperties được thiết kế để xử lý nội dung văn bản. Không áp dụng chúng cho ảnh, archive, tệp nhị phân hoặc dữ liệu mà mọi byte phải được giữ nguyên. Hãy chỉ đưa các tệp mẫu văn bản cần thay thế vào task filtering.

### 8.6. Giá trị chứa ký tự đặc biệt

Khi thay token, giá trị được đưa vào nội dung tệp như văn bản. Nếu đầu ra là XML, JSON, YAML hoặc một định dạng có quy tắc escape riêng, hãy bảo đảm giá trị thay thế hợp lệ với định dạng đích.

Ví dụ, một URL có ký tự `&` có thể dùng trực tiếp trong một tệp properties, nhưng nếu được chèn vào thuộc tính XML thì cần escape theo quy tắc XML. FilterSet không tự chuyển đổi giá trị thành entity XML, JSON string hoặc cú pháp an toàn cho mọi định dạng.

## 9. Ví dụ hoàn chỉnh với FilterSet

Ví dụ dưới đây tạo cấu hình theo môi trường từ một template và filtersfile riêng:

**templates/application.properties.template**

~~~properties
# Generated by Apache Ant. Do not edit this file directly.
application.name=@APP_NAME@
server.port=@SERVER_PORT@
database.url=@DATABASE_URL@
logging.level=@LOG_LEVEL@
~~~

**config/filters/dev.properties**

~~~properties
APP_NAME=Sample App - Development
SERVER_PORT=8081
DATABASE_URL=jdbc:postgresql://localhost:5432/sample_dev
LOG_LEVEL=DEBUG
~~~

**build.xml**

~~~xml
<project name="generate-environment-config" default="generate" basedir=".">
    <property name="template.file"
              location="templates/application.properties.template"/>
    <property name="filters.dir" location="config/filters"/>
    <property name="output.dir" location="build/config"/>

    <target name="validate">
        <fail unless="env"
              message="Specify an environment with -Denv=dev, -Denv=test or -Denv=prod."/>

        <available file="${filters.dir}/${env}.properties"
                   property="filters.available"/>

        <fail unless="filters.available"
              message="No filters file exists for the selected environment."/>
    </target>

    <target name="generate" depends="validate">
        <mkdir dir="${output.dir}/${env}"/>

        <copy file="${template.file}"
              tofile="${output.dir}/${env}/application.properties"
              overwrite="true">
            <filterset>
                <filtersfile file="${filters.dir}/${env}.properties"/>
            </filterset>
        </copy>
    </target>
</project>
~~~

Chạy lệnh:

~~~text
ant -Denv=dev generate
~~~

Tệp được tạo:

~~~properties
# Generated by Apache Ant. Do not edit this file directly.
application.name=Sample App - Development
server.port=8081
database.url=jdbc:postgresql://localhost:5432/sample_dev
logging.level=DEBUG
~~~

Khi chạy `ant -Denv=test generate`, Ant dùng filtersfile test và ghi đầu ra vào thư mục test. Cấu hình prod được tạo theo cách tương tự.

## 10. Thực hành tốt

- Giữ một template chung cho những cấu hình có cùng cấu trúc.
- Tách giá trị môi trường khỏi nội dung mẫu.
- Dùng token riêng như `@DATABASE_URL@` nếu ứng dụng cũng sử dụng cú pháp `${...}`.
- Đặt tên token rõ ràng và thống nhất giữa template và filtersfile.
- Chọn thư mục đầu ra riêng cho từng môi trường để tránh ghi đè nhầm cấu hình.
- Kiểm tra sự tồn tại của tệp giá trị trước khi tạo đầu ra.
- Dùng `overwrite="true"` khi cần bảo đảm đầu ra phản ánh giá trị filter mới nhất.
- Không nạp tuần tự các tệp môi trường có key trùng nhau trong cùng project rồi mong chúng ghi đè.
- Chỉ filtering các tệp văn bản có chủ đích; không filtering dữ liệu nhị phân.
- Với đầu ra có cú pháp riêng như XML hoặc JSON, kiểm tra việc escape giá trị theo định dạng đích.
- Đánh dấu tệp được sinh tự động để người dùng biết cần sửa template hoặc tệp giá trị nguồn, không sửa trực tiếp bản đầu ra.

## 11. Tự kiểm tra quy trình sinh cấu hình

Trước khi đưa target tạo cấu hình vào build chính, hãy tự trả lời:

1. Mẫu dùng token dạng `@TOKEN@` hay property dạng `${property.name}`?
2. Giá trị được nạp bằng `filtersfile` hay `property file`?
3. Tên key và token có khớp chính xác không?
4. Property môi trường có được nạp trước khi ExpandProperties chạy không?
5. Mỗi môi trường có thư mục đầu ra riêng không?
6. Có đang vô tình nạp nhiều tệp có property trùng tên trong cùng project không?
7. Copy có cần `overwrite="true"` để phản ánh thay đổi của filtersfile không?
8. Các tệp được filtering có thực sự là văn bản không?
9. Giá trị thay thế có cần escape theo định dạng đầu ra không?
10. Có bước xác nhận đầu ra không còn token hoặc property placeholder ngoài ý muốn không?

Khi tách rõ mẫu, giá trị môi trường và bước thay thế, Ant có thể tạo các tệp cấu hình nhất quán mà không cần duy trì nhiều bản mẫu gần giống nhau. FilterSet phù hợp với token dành riêng cho bước build; ExpandProperties phù hợp khi muốn dùng trực tiếp property của Ant trong nội dung mẫu.
