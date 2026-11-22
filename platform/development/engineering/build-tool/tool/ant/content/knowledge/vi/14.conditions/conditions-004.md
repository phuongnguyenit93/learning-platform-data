# Kiểm tra hệ điều hành, chuỗi và property đã được đặt

Trong Apache Ant, build file thường cần thay đổi hành vi tùy theo môi trường đang chạy. Ví dụ, một lệnh có thể chỉ hoạt động trên Windows; một bước triển khai chỉ được phép chạy khi `env` có giá trị `prod`; hoặc target kiểm thử tích hợp chỉ cần chạy khi người gọi đã bật một property.

Ant cung cấp **condition** để kiểm tra các điều kiện này. Bạn có thể kiểm tra hệ điều hành, so sánh chuỗi, tìm một đoạn văn bản hoặc xác định một property đã tồn tại hay chưa. Kết quả điều kiện thường được dùng để thiết lập một property, rồi các target khác dựa vào property đó để quyết định có thực hiện công việc hay không.

Bài học này tập trung vào ba nhóm kiểm tra: hệ điều hành, giá trị chuỗi và sự tồn tại của property. Điểm quan trọng là phân biệt **property đã được đặt** với **property có giá trị boolean đúng**; hai khái niệm này không giống nhau trong Ant.

## 1. Condition trong Ant

Condition là một biểu thức trả về kết quả đúng hoặc sai. Ant có nhiều condition type và cho phép lồng chúng trong task `condition`.

Cấu trúc cơ bản:

```xml
<condition property="condition.name">
    <!-- Một condition type -->
</condition>
```

Nếu condition bên trong đúng, Ant thiết lập property `condition.name`. Nếu condition sai, property này không được thiết lập bởi task đó.

Ví dụ:

```xml
<condition property="is.production">
    <equals arg1="${env}" arg2="prod"/>
</condition>
```

Nếu giá trị property `env` bằng `prod`, property `is.production` được đặt. Nếu không, property này không được đặt.

Sau đó, target có thể dùng `if` hoặc `unless`:

```xml
<target name="deploy" if="is.production">
    <echo message="Thực hiện bước deploy production"/>
</target>

<target name="show-dev-help" unless="is.production">
    <echo message="Đây không phải cấu hình production"/>
</target>
```

Trong Ant, `if` và `unless` trên target kiểm tra **sự tồn tại của property**, không kiểm tra chuỗi giá trị của property có phải `true` hay không. Đây là quy tắc quan trọng khi thiết kế điều kiện.

## 2. Kiểm tra hệ điều hành bằng os

Condition `os` kiểm tra thông tin hệ điều hành mà JVM cung cấp, chẳng hạn họ hệ điều hành, tên, kiến trúc và phiên bản.

Ví dụ chỉ thực hiện một target trên Windows:

```xml
<condition property="is.windows">
    <os family="windows"/>
</condition>

<target name="windows-setup" if="is.windows">
    <echo message="Đang chạy bước cấu hình dành cho Windows"/>
</target>
```

Khi Ant chạy trên hệ điều hành thuộc family `windows`, condition đúng và property `is.windows` được thiết lập. Trên môi trường khác, property không được thiết lập nên target bị bỏ qua.

### Các thuộc tính của os

Condition `os` hỗ trợ các thuộc tính để nhận diện môi trường:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `family` | Nhóm hệ điều hành | `windows`, `unix`, `mac` |
| `name` | Tên hệ điều hành do JVM báo cáo | `Windows 11`, `Linux`, tên hệ điều hành cụ thể |
| `arch` | Kiến trúc phần cứng/JVM | `amd64`, `aarch64`, `x86_64` tùy môi trường |
| `version` | Chuỗi phiên bản hệ điều hành | Giá trị JVM báo cáo |

Có thể kết hợp nhiều thuộc tính trong cùng một condition:

```xml
<condition property="windows-x64">
    <os family="windows" arch="amd64"/>
</condition>
```

Khi khai báo nhiều thuộc tính, condition phải thỏa các tiêu chí được cung cấp. Hãy lưu ý rằng giá trị `arch` và `version` phụ thuộc JVM và hệ điều hành; cùng một nền tảng có thể được báo bằng các chuỗi khác nhau giữa các môi trường.

### Phân biệt family với name

`family` hữu ích khi chỉ cần phân biệt nhóm hệ điều hành. Ví dụ, nếu một script shell chạy trên Linux và các hệ Unix tương thích, kiểm tra `family="unix"` thường phù hợp hơn so sánh tên hệ điều hành cụ thể.

Nếu cần hành vi riêng cho macOS, có thể kiểm tra `family="mac"`:

```xml
<condition property="is.mac">
    <os family="mac"/>
</condition>
```

Nếu cần phân biệt một tên hệ điều hành cụ thể, dùng `name`:

```xml
<condition property="is.linux">
    <os name="Linux"/>
</condition>
```

Không nên dựa vào một chuỗi `os.name` cố định nếu mục tiêu là hỗ trợ cả một họ hệ điều hành. Dùng `family` khi có thể để build ít phụ thuộc tên phiên bản cụ thể hơn.

### Chạy target trên mọi hệ điều hành trừ Windows

Có thể dùng condition `not`:

```xml
<condition property="is.non-windows">
    <not>
        <os family="windows"/>
    </not>
</condition>

<target name="run-shell-script" if="is.non-windows">
    <echo message="Chạy script dành cho môi trường không phải Windows"/>
</target>
```

`not` đảo kết quả của condition bên trong. Với những điều kiện phức tạp hơn, Ant còn có `and` và `or`.

## 3. Kiểm tra chuỗi bằng equals

Condition `equals` so sánh hai chuỗi:

```xml
<condition property="is.production">
    <equals arg1="${env}" arg2="prod"/>
</condition>
```

Nếu `env` có giá trị chính xác là `prod`, property `is.production` được thiết lập.

Có thể dùng thuộc tính `casesensitive` để quy định so sánh có phân biệt chữ hoa/chữ thường hay không:

```xml
<condition property="is.production">
    <equals
        arg1="${env}"
        arg2="PROD"
        casesensitive="false"/>
</condition>
```

Với `casesensitive="false"`, các giá trị như `prod`, `PROD` hoặc `Prod` có thể được xem là bằng nhau. Nếu chữ hoa/chữ thường có ý nghĩa trong cấu hình, hãy khai báo `casesensitive` tường minh để build file dễ đọc.

### So sánh chuỗi rỗng

`equals` cũng có thể kiểm tra một chuỗi rỗng:

```xml
<condition property="has.no.profile">
    <equals arg1="${profile}" arg2=""/>
</condition>
```

Tuy nhiên, nếu `profile` chưa được thiết lập, biểu thức ${profile}` có thể vẫn còn nguyên trong chuỗi sau khi thay thế property. Nếu mục tiêu là kiểm tra property có tồn tại hay không, hãy dùng `isset`; nếu mục tiêu là so sánh giá trị, hãy bảo đảm property được thiết lập trước.

## 4. Kiểm tra một chuỗi có chứa đoạn văn bản bằng contains

Condition `contains` kiểm tra một chuỗi có chứa một đoạn con hay không:

```xml
<condition property="uses.json">
    <contains
        string="${dependencies}"
        substring="json"/>
</condition>
```

Nếu giá trị `dependencies` chứa chuỗi `json`, property `uses.json` được thiết lập.

Có thể cấu hình so sánh không phân biệt hoa thường:

```xml
<condition property="mentions.windows">
    <contains
        string="${platform.description}"
        substring="windows"
        casesensitive="false"/>
</condition>
```

Condition này hữu ích với các chuỗi mô tả hoặc giá trị cấu hình đơn giản. Không nên dùng `contains` để phân tích một định dạng phức tạp như danh sách dependency có quy tắc quoting hoặc phân tách riêng; khi đó hãy dùng một cơ chế phân tích dữ liệu phù hợp.

## 5. Kiểm tra property đã được đặt bằng isset

Condition `isset` kiểm tra một property có tồn tại trong Project của Ant hay không:

```xml
<condition property="has.deploy.host">
    <isset property="deploy.host"/>
</condition>
```

Nếu property `deploy.host` đã được thiết lập, kể cả giá trị là chuỗi rỗng, condition vẫn đúng.

Ví dụ:

```xml
<property name="empty.value" value=""/>

<condition property="empty.is.set">
    <isset property="empty.value"/>
</condition>

<condition property="missing.is.set">
    <isset property="missing.value"/>
</condition>

<target name="show">
    <echo message="empty.value exists: ${empty.is.set}"/>
    <echo message="missing.value exists: ${missing.is.set}"/>
</target>
```

Property `empty.value` đã được khai báo nên `empty.is.set` được thiết lập. `missing.value` chưa tồn tại nên `missing.is.set` không được thiết lập.

### isset không kiểm tra giá trị boolean

Đây là điểm dễ nhầm nhất:

```bash
ant -Dfeature.enabled=false show
```

Lệnh trên vẫn tạo một user property có tên `feature.enabled`. Vì vậy:

```xml
<condition property="feature.was.provided">
    <isset property="feature.enabled"/>
</condition>
```

condition vẫn đúng dù giá trị property là chuỗi `false`.

Nếu bạn muốn kiểm tra property đã được truyền hay chưa, dùng `isset`. Nếu muốn kiểm tra giá trị có phải boolean true hay không, dùng `istrue` hoặc so sánh bằng `equals`.

### Phân biệt isset, if và unless

| Cơ chế | Điều được kiểm tra |
|---|---|
| `<isset property="x"/>` | Property `x` có tồn tại không |
| `<target if="x">` | Target chạy nếu property `x` tồn tại |
| `<target unless="x">` | Target chạy nếu property `x` không tồn tại |
| `<equals arg1="PROPERTY_VALUE" arg2="true"/>` | Giá trị chuỗi của property có bằng `true` không |

Ví dụ:

```xml
<target name="feature-info" if="feature.enabled">
    <echo message="Property feature.enabled đã được đặt"/>
</target>
```

Target trên vẫn chạy nếu người gọi truyền `-Dfeature.enabled=false`, vì Ant chỉ kiểm tra property có tồn tại.

## 6. Kiểm tra giá trị boolean bằng istrue và isfalse

Nếu property được dùng như cờ bật/tắt, condition `istrue` và `isfalse` diễn đạt ý định rõ hơn `isset`.

Ví dụ:

```xml
<condition property="run.integration">
    <istrue value="${integration.enabled}"/>
</condition>

<target name="integration-test" if="run.integration">
    <echo message="Chạy integration tests"/>
</target>
```

`istrue` kiểm tra giá trị có được Ant nhận diện là true hay không. Condition `isfalse` kiểm tra giá trị được nhận diện là false:

```xml
<condition property="skip.integration">
    <isfalse value="${integration.enabled}"/>
</condition>
```

Các condition boolean nhận biết một số cách viết tương đương như `true`/`false`, `yes`/`no` hoặc `on`/`off` theo quy tắc của Ant. Nếu ứng dụng chỉ cho phép đúng hai chuỗi `true` và `false`, dùng `equals` để kiểm tra chính xác thay vì chấp nhận các cách viết boolean khác.

Nếu property có thể chưa tồn tại, hãy thiết lập giá trị mặc định hoặc kiểm tra sự tồn tại trước khi dùng giá trị đó trong condition. Điều này giúp tránh việc một property chưa được cung cấp bị hiểu nhầm thành một cấu hình hợp lệ.

## 7. Kết hợp nhiều condition bằng and, or và not

Condition có thể lồng nhau để diễn đạt một quy tắc gồm nhiều tiêu chí.

### and: tất cả điều kiện phải đúng

Ví dụ chỉ cho phép triển khai khi đang ở môi trường production, có host và chạy trên Windows:

```xml
<condition property="can.deploy">
    <and>
        <equals arg1="${env}" arg2="prod"/>
        <isset property="deploy.host"/>
        <os family="windows"/>
    </and>
</condition>
```

Property `can.deploy` chỉ được thiết lập khi cả ba condition con đều đúng.

### or: chỉ cần một điều kiện đúng

Ví dụ bật target khi môi trường là macOS hoặc Unix:

```xml
<condition property="supports.posix.tools">
    <or>
        <os family="mac"/>
        <os family="unix"/>
    </or>
</condition>
```

### not: đảo kết quả

Ví dụ kiểm tra môi trường không phải production:

```xml
<condition property="is.not.production">
    <and>
        <isset property="env"/>
        <not>
            <equals arg1="${env}" arg2="prod"/>
        </not>
    </and>
</condition>
```

### Kết hợp lồng nhau

Bạn có thể kết hợp `and`, `or`, `not` để diễn đạt quy tắc rõ ràng:

```xml
<condition property="can.run.local.tool">
    <and>
        <not>
            <os family="windows"/>
        </not>
        <or>
            <os family="mac"/>
            <os family="unix"/>
        </or>
        <isset property="tool.home"/>
    </and>
</condition>
```

Trong ví dụ này, property được thiết lập nếu môi trường thuộc macOS hoặc Unix, không phải Windows và property `tool.home` đã tồn tại. Khi xây dựng condition lồng nhau, hãy chia mỗi nhóm thành một mục tiêu rõ ràng để người đọc dễ hiểu và bảo trì.

## 8. Ví dụ đầy đủ: chọn target theo hệ điều hành và cấu hình

Build file sau chọn một target chuẩn bị khác nhau tùy theo hệ điều hành:

```xml
<project name="platform-build" default="build" basedir=".">

    <property name="env" value="dev"/>
    <property name="output.dir" value="build"/>

    <condition property="is.windows">
        <os family="windows"/>
    </condition>

    <condition property="is.unix">
        <os family="unix"/>
    </condition>

    <condition property="is.production">
        <equals arg1="${env}" arg2="prod"/>
    </condition>

    <target name="prepare-windows" if="is.windows">
        <echo message="Chuẩn bị môi trường Windows"/>
        <mkdir dir="${output.dir}/windows"/>
    </target>

    <target name="prepare-unix" if="is.unix">
        <echo message="Chuẩn bị môi trường Unix"/>
        <mkdir dir="${output.dir}/unix"/>
    </target>

    <target name="build" depends="prepare-windows,prepare-unix">
        <echo message="Build environment: ${env}"/>
    </target>

    <target name="deploy" if="is.production">
        <echo message="Triển khai production"/>
    </target>

</project>
```

Chạy mặc định:

```bash
ant
```

Ant thiết lập `env=dev`, nhận diện hệ điều hành và chạy target chuẩn bị phù hợp.

Chạy cho production:

```bash
ant -Denv=prod deploy
```

Condition `is.production` được đánh giá dựa trên giá trị `env` đã có từ dòng lệnh. Nếu giá trị bằng `prod`, target `deploy` được thực hiện.

Ví dụ này minh họa cách tách phần nhận diện môi trường ra khỏi logic của target. Khi cần thay đổi quy tắc, bạn có thể chỉnh condition tại một nơi mà không phải lặp lại điều kiện trong nhiều task.

## 9. Chẩn đoán khi condition không hoạt động như mong đợi

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Target `if` vẫn chạy dù property bằng `false` | `if` kiểm tra sự tồn tại, không kiểm tra giá trị | Dùng `istrue` hoặc `equals` để tạo property điều kiện |
| Target bị bỏ qua dù đã truyền property | Sai tên property hoặc condition tạo property không đúng | In giá trị đầu vào và kiểm tra tên property |
| Condition `os` không khớp | JVM báo `os.name`, `os.arch` hoặc family khác dự kiến | In các system property và dùng `family` phù hợp |
| So sánh chuỗi thất bại | Khác chữ hoa/thường, khoảng trắng hoặc giá trị thực tế | In chuỗi trong dấu ngoặc và kiểm tra `casesensitive` |
| `isset` trả về đúng với giá trị `false` | Property tồn tại dù nội dung là chuỗi `false` | Đây là hành vi đúng; dùng condition kiểm tra giá trị |
| Property condition đã có từ trước nên kết quả không đổi | Property có tính bất biến hoặc user property đã được truyền | Dùng tên property kết quả riêng và không truyền nó từ bên ngoài |
| Condition dùng property chưa có giá trị | Property chưa được nạp trước thời điểm đánh giá | Đặt giá trị mặc định hoặc nạp cấu hình trước condition |

Có thể in thông tin môi trường để quan sát:

```xml
<target name="show-platform">
    <echo message="os.name=${os.name}"/>
    <echo message="os.arch=${os.arch}"/>
    <echo message="os.version=${os.version}"/>
    <echo message="env=${env}"/>
</target>
```

`os.name`, `os.arch` và `os.version` là các system property do JVM cung cấp. Chúng giúp giải thích vì sao một condition nhận diện hệ điều hành không khớp như mong đợi.

Để kiểm tra property đã được truyền từ dòng lệnh, chạy:

```bash
ant -Dfeature.enabled=false show-platform
```

Sau đó dùng `isset` để kiểm tra sự tồn tại và `istrue`/`equals` để kiểm tra nội dung. Hai bước này giúp phân biệt lỗi ở đầu vào với lỗi trong biểu thức điều kiện.

## 10. Các nguyên tắc nên áp dụng

- Dùng `os family` khi chỉ cần nhận diện một nhóm hệ điều hành; chỉ dùng `name`, `arch` hoặc `version` khi cần phân biệt cụ thể.
- Dùng `equals` để so sánh chuỗi chính xác; khai báo `casesensitive` tường minh nếu quy tắc chữ hoa/chữ thường quan trọng.
- Dùng `contains` khi cần kiểm tra một đoạn văn bản nằm trong chuỗi.
- Dùng `isset` khi cần biết người gọi đã cung cấp property hay chưa.
- Dùng `istrue` hoặc `isfalse` khi property mang ý nghĩa bật/tắt.
- Nhớ rằng `if` và `unless` trên target kiểm tra property có tồn tại hay không.
- Dùng `and`, `or`, `not` để kết hợp condition; đặt tên property kết quả theo ý nghĩa nghiệp vụ.
- Đừng dùng property kết quả condition như một cờ đầu vào mà người gọi có thể truyền tùy ý, vì property được truyền trước có thể ảnh hưởng kết quả do tính bất biến.
- In giá trị thực tế khi chẩn đoán, đặc biệt với tên hệ điều hành, kiến trúc và chuỗi cấu hình.

## 11. Ghi nhớ

- `<condition property="...">` đánh giá condition con và thiết lập property kết quả khi biểu thức đúng.
- `<os>` kiểm tra family, name, arch hoặc version của hệ điều hành.
- `<equals>` so sánh hai chuỗi; `<contains>` kiểm tra chuỗi có chứa đoạn con.
- `<isset>` kiểm tra property có tồn tại, kể cả khi giá trị của nó là chuỗi rỗng hoặc `false`.
- `<istrue>` và `<isfalse>` kiểm tra nội dung theo quy tắc boolean của Ant.
- `if` và `unless` trên target chỉ dựa vào sự tồn tại của property, không diễn giải giá trị như boolean.
- `<and>`, `<or>` và `<not>` giúp kết hợp nhiều điều kiện.
- Property Ant có tính bất biến; hãy thiết lập đầu vào trước khi condition được đánh giá và dùng tên riêng cho các kết quả tính toán.

Khi viết build file, hãy tách rõ việc nhận diện môi trường, kiểm tra giá trị cấu hình và kiểm tra property đã được cung cấp. Dùng đúng condition type cho từng mục đích sẽ giúp target chạy có thể dự đoán được trên Windows, macOS, Linux và các môi trường CI khác.
