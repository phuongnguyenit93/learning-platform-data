# Tham số macro với attribute và cú pháp `@{...}`

Khi nhiều target trong build file cần thực hiện cùng một nhóm task nhưng khác đường dẫn, tên module hoặc chế độ xử lý, việc sao chép toàn bộ đoạn XML sẽ làm build file dài và khó bảo trì. Apache Ant cung cấp `<macrodef>` để định nghĩa một task tái sử dụng. Macro nhận tham số qua các phần tử `<attribute>`; bên trong thân macro, giá trị tham số được tham chiếu bằng cú pháp `@{tên-tham-số}`.

Macro giúp gom một chuỗi task có cấu trúc giống nhau thành một định nghĩa duy nhất. Mỗi lần gọi macro, ta truyền các giá trị khác nhau để tạo ra hành động tương ứng. Cơ chế này hữu ích khi build nhiều module, nhiều thư mục source, nhiều bộ cấu hình hoặc nhiều artifact theo cùng một quy trình.

## 1. Khai báo macro bằng `<macrodef>`

Một macro cơ bản có tên, danh sách attribute và phần `<sequential>` chứa các task sẽ được thực hiện khi macro được gọi:

```xml
<macrodef name="say-hello">
    <attribute name="name"/>

    <sequential>
        <echo message="Hello, @{name}!"/>
    </sequential>
</macrodef>
```

`<macrodef>` đăng ký một task tên `say-hello`. Attribute `name` là tham số của task đó. Khi gọi:

```xml
<say-hello name="Ant developer"/>
```

Ant thay `@{name}` trong thân macro bằng `Ant developer`, sau đó thực thi task `<echo>` tương ứng. Kết quả là:

```text
Hello, Ant developer!
```

Một macro có thể chứa nhiều task. Các task trong `<sequential>` được thực thi theo thứ tự khi macro được gọi:

```xml
<macrodef name="prepare-directory">
    <attribute name="directory"/>

    <sequential>
        <echo message="Preparing @{directory}"/>
        <mkdir dir="@{directory}"/>
        <echo message="Directory is ready"/>
    </sequential>
</macrodef>

<target name="prepare">
    <prepare-directory directory="build/classes"/>
    <prepare-directory directory="build/test-classes"/>
</target>
```

Hai lần gọi dùng cùng một quy trình nhưng tạo hai thư mục khác nhau. Macro không tự chạy khi được định nghĩa; nó chỉ thực hiện khi có task invocation như `<prepare-directory .../>` trong target hoặc trong một macro khác.

## 2. Attribute bắt buộc và attribute có giá trị mặc định

Phần tử `<attribute>` khai báo một tham số mà macro nhận từ nơi gọi. Nếu không có `default`, tham số là bắt buộc. Nếu có `default`, người gọi có thể bỏ qua và macro dùng giá trị mặc định.

```xml
<macrodef name="compile-source">
    <attribute name="source"/>
    <attribute name="destination" default="build/classes"/>
    <attribute name="debug" default="false"/>

    <sequential>
        <mkdir dir="@{destination}"/>
        <javac srcdir="@{source}"
               destdir="@{destination}"
               debug="@{debug}"
               includeantruntime="false"/>
    </sequential>
</macrodef>
```

Trong định nghĩa này:

- `source` bắt buộc phải được truyền vào mỗi lần gọi.
- `destination` mặc định là `build/classes`.
- `debug` mặc định là `false`.

Có thể gọi macro theo hai cách:

```xml
<target name="compile">
    <!-- Dùng destination và debug mặc định. -->
    <compile-source source="src/main/java"/>

    <!-- Ghi đè cả hai giá trị mặc định. -->
    <compile-source source="src/generated/java"
                    destination="build/generated-classes"
                    debug="true"/>
</target>
```

Nếu macro được gọi mà thiếu attribute bắt buộc, Ant báo lỗi khi thực thi lời gọi macro. Giá trị mặc định giúp tránh lặp lại các tham số phổ biến, trong khi các thuộc tính quan trọng không có default buộc người gọi cung cấp rõ ràng.

`default` có thể là chuỗi rỗng nếu muốn tham số không bắt buộc nhưng mặc định không có nội dung:

```xml
<macrodef name="copy-optional-config">
    <attribute name="source"/>
    <attribute name="destination" default="build/config.properties"/>

    <sequential>
        <echo message="Copy source @{source}"/>
        <copy file="@{source}" tofile="@{destination}"/>
    </sequential>
</macrodef>
```

Trong ví dụ này, nếu không truyền `destination`, file được sao chép tới `build/config.properties`. Người gọi có thể truyền đường dẫn khác khi cần. Chọn default sao cho task bên trong luôn nhận được giá trị hợp lệ.

## 3. Thay thế tham số bằng cú pháp `@{...}`

`@{attribute-name}` là cú pháp tham chiếu attribute riêng của MacroDef. Khi Ant tạo một lần thực thi macro, nó thay placeholder này bằng giá trị được truyền vào hoặc giá trị default.

```xml
<macrodef name="package-module">
    <attribute name="module"/>
    <attribute name="version" default="1.0.0"/>

    <sequential>
        <echo message="Packaging module @{module}, version @{version}"/>
        <mkdir dir="build/packages/@{module}"/>
        <jar destfile="build/packages/@{module}/@{module}-@{version}.jar"
             basedir="build/classes/@{module}"/>
    </sequential>
</macrodef>

<target name="package">
    <package-module module="customer" version="2.1.0"/>
    <package-module module="invoice" version="3.0.0"/>
</target>
```

Khi macro chạy cho `customer`, các placeholder được thay bằng `customer` và `2.1.0`. Lần gọi cho `invoice` tạo một JAR khác với version `3.0.0`. Cùng một định nghĩa có thể dùng nhiều lần mà không phải sao chép các task `<mkdir>` và `<jar>`.

Tên trong `@{...}` phải khớp với tên attribute đã khai báo trong macro. Nếu viết sai tên hoặc tham chiếu một attribute chưa được khai báo, macro không có giá trị tương ứng để thay thế và thường sẽ để lại chuỗi không mong muốn trong cấu hình task, dẫn tới lỗi ở task được tạo. Hãy giữ tên attribute ngắn, có nghĩa và nhất quán.

### Không nhầm `@{...}` với `${...}`

Ant có hai cơ chế thay thế thường xuất hiện cạnh nhau:

| Cú pháp | Ý nghĩa | Nguồn giá trị |
|---|---|---|
| `${property}` | Thay Ant property | Property đã được khai báo bằng `<property>`, command line `-D` hoặc cơ chế tương ứng |
| `@{attribute}` | Thay tham số macro | Attribute được khai báo trong `<macrodef>` và truyền ở lần gọi macro |

Ví dụ:

```xml
<property name="build.dir" location="build"/>

<macrodef name="compile-module">
    <attribute name="module"/>

    <sequential>
        <javac srcdir="src/@{module}"
               destdir="${build.dir}/classes/@{module}"
               includeantruntime="false"/>
    </sequential>
</macrodef>

<target name="compile">
    <compile-module module="customer"/>
</target>
```

`module` thay đổi theo mỗi lần gọi macro nên dùng `@{module}`. `build.dir` là cấu hình chung của build nên dùng `${build.dir}`. Có thể dùng cả hai cú pháp trong cùng một thuộc tính XML như `destdir` ở ví dụ trên.

Không thể thay `${build.dir}` bằng `@{build.dir}` trừ khi macro có khai báo attribute tên `build.dir`. Ngược lại, khai báo Ant property `module` không tự tạo attribute `@{module}` cho macro.

## 4. Tái sử dụng macro với nhiều tham số

Macro thường nhận nhiều attribute để mô tả các phần khác nhau của cùng một quy trình. Ví dụ sau đóng gói một module với tên, thư mục class, thư mục output và main class:

```xml
<property name="dist.dir" location="build/distribution"/>

<macrodef name="build-executable-jar">
    <attribute name="name"/>
    <attribute name="classes"/>
    <attribute name="main-class"/>
    <attribute name="version" default="1.0.0"/>

    <sequential>
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/@{name}-@{version}.jar"
             basedir="@{classes}">
            <manifest>
                <attribute name="Main-Class" value="@{main-class}"/>
                <attribute name="Implementation-Title" value="@{name}"/>
                <attribute name="Implementation-Version" value="@{version}"/>
            </manifest>
        </jar>
    </sequential>
</macrodef>

<target name="package-all">
    <build-executable-jar name="customer-service"
                          classes="build/classes/customer"
                          main-class="com.example.customer.Main"
                          version="2.1.0"/>

    <build-executable-jar name="invoice-service"
                          classes="build/classes/invoice"
                          main-class="com.example.invoice.Main"
                          version="3.0.0"/>
</target>
```

Các attribute mô tả dữ liệu khác nhau; các task bên trong macro mô tả quy trình chung. Khi cần thay đổi cách tạo JAR, chỉ cần sửa định nghĩa `build-executable-jar` thay vì sửa từng nơi gọi.

Nếu danh sách tham số tăng quá nhiều, hãy cân nhắc gom cấu hình chung thành Ant property hoặc dùng nested element để người gọi truyền một cấu trúc phức tạp hơn. Macro với quá nhiều attribute thường khó đọc và dễ bị gọi sai.

## 5. Kiểm soát mở rộng property bằng `doubleexpanding`

Attribute của MacroDef có thuộc tính `doubleexpanding` (từ Ant 1.8.3) để kiểm soát việc mở rộng Ant property trong giá trị attribute. Mặc định là `true`: giá trị attribute có thể được mở rộng khi macro được gọi và một lần nữa khi nội dung macro được thực thi. Đặt `doubleexpanding="false"` để tắt lần mở rộng thứ hai.

Điểm này quan trọng khi giá trị macro có chứa biểu thức `${...}` cần được giữ lại cho một giai đoạn xử lý sau, hoặc khi macro được lồng trong một macro khác. Nếu không kiểm soát, biểu thức property có thể được thay thế sớm hơn thời điểm mong muốn.

Ví dụ khai báo attribute không mở rộng lần thứ hai:

```xml
<macrodef name="write-template-reference">
    <attribute name="expression" doubleexpanding="false"/>

    <sequential>
        <echo message="Template expression: @{expression}"/>
    </sequential>
</macrodef>
```

`doubleexpanding` không thay đổi vai trò của `@{expression}`: placeholder vẫn được thay bằng giá trị attribute. Nó chỉ điều khiển số lần Ant mở rộng property expression `${...}` nằm bên trong giá trị đó. Hãy giữ mặc định khi cần hành vi mở rộng thông thường; chỉ đặt `false` khi có yêu cầu giữ biểu thức để xử lý ở một giai đoạn khác.

Khi làm việc với macro lồng nhau hoặc chuỗi có chứa `${...}` theo nghĩa đen, nên tạo một ví dụ nhỏ và quan sát output thực tế. Điều này giúp xác định biểu thức được thay ở thời điểm gọi macro hay trong lần thực thi tiếp theo.

## 6. Attribute và nested element

Attribute phù hợp với giá trị đơn như tên module, version, đường dẫn hoặc cờ bật/tắt. Khi macro cần nhận một cấu trúc XML như classpath hoặc danh sách file, có thể khai báo nested element bằng `<element>` thay vì cố gắng truyền toàn bộ cấu trúc qua một chuỗi attribute.

Ví dụ:

```xml
<macrodef name="compile-with-extra-classpath">
    <attribute name="source"/>
    <attribute name="destination" default="build/classes"/>
    <element name="extra-classpath" optional="true"/>

    <sequential>
        <mkdir dir="@{destination}"/>
        <javac srcdir="@{source}"
               destdir="@{destination}"
               includeantruntime="false">
            <classpath>
                <pathelement location="lib/common.jar"/>
                <extra-classpath/>
            </classpath>
        </javac>
    </sequential>
</macrodef>

<target name="compile">
    <compile-with-extra-classpath source="src/main/java">
        <extra-classpath>
            <pathelement location="lib/database-driver.jar"/>
            <pathelement location="lib/logging-api.jar"/>
        </extra-classpath>
    </compile-with-extra-classpath>
</target>
```

Macro nhận `source` và `destination` qua attribute, còn `extra-classpath` là một nested element có thể chứa nhiều phần tử `pathelement`. Từ khóa `optional="true"` cho phép không truyền nested element đó; nếu bỏ `optional`, phần tử là bắt buộc theo mặc định.

Có thể khai báo `implicit="true"` cho element để các phần tử con trực tiếp của lời gọi macro được đưa vào vị trí element đó mà không cần bọc trong thẻ cùng tên. Cách này tiện nhưng làm cấu trúc invocation kém tường minh; chỉ dùng khi macro có một vùng nested content rõ ràng.

## 7. Phạm vi và tổ chức macro

MacroDef là cách tạo task tùy chỉnh ở cấp build file. Nó không tạo target, không tự thêm dependency giữa các target và không tự quyết định khi nào chạy. Macro invocation chạy tại vị trí nó xuất hiện trong target hoặc trong nội dung build được thực thi.

Nên đặt các macro dùng chung ở gần đầu build file hoặc trong file build được import để người đọc tìm thấy định nghĩa trước khi xem nơi gọi. Tên macro nên mô tả hành động, ví dụ `compile-module`, `copy-config` hoặc `build-executable-jar`; tên attribute nên mô tả dữ liệu mà người gọi cần cung cấp.

Khi một macro trở nên phức tạp, hãy tách quy trình thành những macro nhỏ hơn hoặc target có dependency rõ ràng. Macro phù hợp để tái sử dụng một nhóm task có cùng cấu trúc; target phù hợp hơn khi cần mô tả một giai đoạn build có tên, có thể được gọi độc lập và có quan hệ `depends` với các target khác.

## 8. Lỗi thường gặp và cách xử lý

1. **Dùng `${name}` thay cho `@{name}` trong macro.** `${name}` tìm Ant property; nó không tham chiếu attribute của macro. Dùng `@{name}` cho tham số khai báo bằng `<attribute>`.
2. **Gọi macro thiếu attribute bắt buộc.** Thêm giá trị ở invocation hoặc khai báo `default` nếu có giá trị mặc định hợp lý.
3. **Tên placeholder không khớp.** Đảm bảo `@{sourceDir}` khớp chính xác với `<attribute name="sourceDir"/>`.
4. **Đặt default không phù hợp.** Giá trị mặc định rỗng có thể khiến task con nhận đường dẫn không hợp lệ. Chỉ đặt default khi macro có thể xử lý giá trị đó.
5. **Sao chép XML thay vì truyền tham số.** Nếu chỉ khác tên module hoặc đường dẫn, hãy đưa phần khác biệt thành attribute để dùng chung quy trình.
6. **Macro có quá nhiều attribute.** Khi tham số trở nên khó hiểu, gom cấu hình chung vào property hoặc dùng nested element cho dữ liệu có cấu trúc.
7. **Property bị mở rộng sai thời điểm.** Kiểm tra `doubleexpanding`; đặt `false` nếu cần bỏ lần mở rộng thứ hai và giữ biểu thức cho giai đoạn sau.
8. **Nhầm macro với target.** Macro là task tùy chỉnh được gọi tại vị trí xuất hiện; target là đơn vị thực thi có tên và có thể khai báo `depends`, `if`, `unless`.
9. **Đưa nhiều nested element nhưng không khai báo `<element>`.** Nếu macro cần nhận XML lồng, khai báo element trong định nghĩa và dùng placeholder element tương ứng trong thân macro.
10. **Dùng macro để che một quy trình quá lớn.** Giữ macro tập trung vào một thao tác có cấu trúc ổn định để invocation vẫn dễ đọc.

## 9. Quy trình thiết kế macro có tham số

Khi chuyển một đoạn XML lặp lại thành macro, có thể thực hiện theo trình tự:

1. Tìm các task có cấu trúc giống nhau và xác định phần nào thực sự thay đổi giữa các lần dùng.
2. Đưa mỗi giá trị đơn cần thay đổi thành một `<attribute>` có tên dễ hiểu.
3. Chọn attribute bắt buộc hay có `default` dựa trên yêu cầu của task.
4. Thay các giá trị thay đổi trong `<sequential>` bằng `@{attribute-name}`.
5. Giữ các cấu hình dùng chung dưới dạng Ant property `${property}`.
6. Nếu cần nhận danh sách hoặc cấu trúc XML, khai báo `<element>` và dùng nested element placeholder.
7. Gọi macro từ target với các giá trị cụ thể; kiểm tra mỗi lần gọi tạo đúng đường dẫn và artifact mong muốn.
8. Chỉ điều chỉnh `doubleexpanding` khi có yêu cầu rõ ràng về thời điểm mở rộng property.

## Tài liệu tham khảo

- [Apache Ant Manual — MacroDef Task](https://ant.apache.org/manual/Tasks/macrodef.html): định nghĩa macro, attribute, default value, nested element và cú pháp `@{...}`.
- [Apache Ant Manual — Property Task](https://ant.apache.org/manual/Tasks/property.html): khai báo và mở rộng Ant property bằng cú pháp `${...}`.
- [Apache Ant Manual — Javac Task](https://ant.apache.org/manual/Tasks/javac.html): ví dụ task được tái sử dụng trong macro để biên dịch mã Java.
