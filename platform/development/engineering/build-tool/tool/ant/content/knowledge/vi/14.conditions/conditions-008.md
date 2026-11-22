# Điều kiện trên task bằng namespace `ant:if` và `ant:unless`

Trong một build file Apache Ant, có những task chỉ cần chạy khi một tính năng được bật, một property đã được khai báo hoặc một giá trị đầu vào không rỗng. Trước đây, điều kiện thường được đặt ở cấp `<target>`. Từ Ant 1.9.1, ta có thể gắn điều kiện trực tiếp lên task và cả phần tử lồng bên trong task bằng hai namespace đặc biệt `ant:if` và `ant:unless`.

Cách viết này giúp build file thể hiện điều kiện ngay tại nơi hành động xảy ra. Ví dụ, task `<echo>` có thể chỉ chạy khi chế độ debug được bật; hoặc một `<arg>` chỉ được thêm vào lệnh `<exec>` khi người dùng yêu cầu tham số mở rộng.

## 1. Khai báo hai namespace

Khai báo hai namespace ở phần tử gốc `<project>` để các task và phần tử con trong build file có thể dùng chúng:

```xml
<project name="conditional-tasks"
         default="demo"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">
    <!-- targets and tasks -->
</project>
```

Hai URI namespace phải đúng nguyên văn:

| Prefix | Namespace URI | Ý nghĩa |
|---|---|---|
| `if` | `ant:if` | Giữ phần tử khi điều kiện đúng |
| `unless` | `ant:unless` | Giữ phần tử khi điều kiện phủ định là đúng |

Prefix `if` và `unless` là tên ngắn được khai báo trong XML. Phần quan trọng để Ant nhận diện tính năng là namespace URI `ant:if` và `ant:unless`. Nếu dùng thuộc tính có prefix mà quên khai báo namespace tương ứng, XML parser sẽ báo lỗi. Tính năng này cần Apache Ant 1.9.1 trở lên.

## 2. Ba loại điều kiện

Mỗi namespace hỗ trợ ba hậu tố: `true`, `blank` và `set`. Ghép hậu tố với prefix sẽ tạo thành sáu dạng thuộc tính:

| Thuộc tính | Phần tử được giữ khi | Ví dụ |
|---|---|---|
| `if:true` | Giá trị thuộc tính được đánh giá là `true` | `if:true="${feature.enabled}"` |
| `unless:true` | Giá trị thuộc tính được đánh giá là `false` | `unless:true="${feature.enabled}"` |
| `if:blank` | Giá trị thuộc tính là `null` hoặc chuỗi rỗng | `if:blank="${report.name}"` |
| `unless:blank` | Giá trị thuộc tính không rỗng | `unless:blank="${report.name}"` |
| `if:set` | Property có tên được chỉ định đã được khai báo | `if:set="feature.enabled"` |
| `unless:set` | Property có tên được chỉ định chưa được khai báo | `unless:set="feature.enabled"` |

### `true`: kiểm tra giá trị đúng hoặc sai

`if:true` và `unless:true` dùng để kiểm tra giá trị sau khi Ant thay thế property. Đây là lựa chọn phù hợp khi property mang ý nghĩa bật/tắt và có giá trị boolean rõ ràng.

```xml
<project name="boolean-condition"
         default="show"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="feature.enabled" value="true"/>
    <property name="debug.enabled" value="false"/>

    <target name="show">
        <echo message="Tính năng đang bật"
              if:true="${feature.enabled}"/>

        <echo message="Tính năng đang tắt"
              unless:true="${feature.enabled}"/>

        <echo message="Thông tin debug được bật"
              if:true="${debug.enabled}"/>

        <echo message="Thông tin debug bị tắt"
              unless:true="${debug.enabled}"/>
    </target>
</project>
```

Với các giá trị trên, hai thông báo về `feature.enabled` và thông báo `debug.enabled` bị tắt sẽ được in ra. Hai task còn lại bị bỏ qua. Nên dùng các giá trị boolean tường minh như `true` và `false` để người đọc dễ hiểu ý định của build file.

Điểm cần nhớ là `if:true` kiểm tra **giá trị** của biểu thức, không kiểm tra property có tồn tại hay không. Nếu cần kiểm tra sự tồn tại, hãy dùng `if:set`.

### `set`: kiểm tra property đã được khai báo

`if:set` và `unless:set` kiểm tra sự tồn tại của property. Giá trị hiện tại của property không ảnh hưởng đến kết quả kiểm tra này.

```xml
<project name="property-existence"
         default="show"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="debug.enabled" value="false"/>

    <target name="show">
        <echo message="debug.enabled đã được khai báo"
              if:set="debug.enabled"/>

        <echo message="publish.enabled chưa được khai báo"
              unless:set="publish.enabled"/>
    </target>
</project>
```

Task đầu tiên vẫn chạy mặc dù `debug.enabled` có giá trị `false`, bởi vì property này đã tồn tại. Đây là khác biệt quan trọng giữa hai cách viết:

```xml
<!-- Chạy khi property tồn tại, kể cả khi giá trị là false hoặc chuỗi rỗng. -->
<echo message="Property đã tồn tại" if:set="feature.enabled"/>

<!-- Chạy khi giá trị của property được đánh giá là true. -->
<echo message="Feature đang bật" if:true="${feature.enabled}"/>
```

Ở dạng `set`, giá trị là **tên property**, vì vậy viết `if:set="feature.enabled"`, không viết `if:set="${feature.enabled}"`. Ngược lại, `true` và `blank` kiểm tra giá trị của biểu thức nên thường dùng property expansion `${...}`.

### `blank`: kiểm tra giá trị rỗng

`if:blank` và `unless:blank` kiểm tra giá trị của thuộc tính sau khi Ant xử lý property expansion. Dùng `if:blank` khi muốn xử lý trường hợp không có nội dung; dùng `unless:blank` khi chỉ muốn tạo phần tử khi đã có nội dung.

```xml
<project name="blank-condition"
         default="show"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="report.name" value=""/>
    <property name="output.directory" value="build/reports"/>

    <target name="show">
        <echo message="Chưa đặt tên báo cáo"
              if:blank="${report.name}"/>

        <echo message="Báo cáo: ${report.name}"
              unless:blank="${report.name}"/>

        <mkdir dir="${output.directory}"
               unless:blank="${output.directory}"/>
    </target>
</project>
```

Vì `report.name` là chuỗi rỗng, task đầu tiên chạy còn task thứ hai bị bỏ qua. `mkdir` chỉ được đưa vào build khi `output.directory` có giá trị. Nếu mục tiêu là kiểm tra property có được khai báo hay chưa, dùng `if:set` hoặc `unless:set`; `blank` kiểm tra nội dung giá trị, không thay thế cho phép kiểm tra sự tồn tại.

## 3. Gắn điều kiện vào task và phần tử lồng

Điều kiện áp dụng tại đúng phần tử mang thuộc tính đó. Nếu đặt điều kiện lên một task, Ant bỏ qua toàn bộ task khi điều kiện không đạt. Nếu đặt điều kiện lên một phần tử con, chỉ phần tử con đó bị bỏ qua; task cha và các phần tử anh em vẫn được xử lý bình thường.

Ví dụ sau minh họa một lệnh Java có tham số tùy chọn:

```xml
<project name="conditional-arguments"
         default="run"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="diagnostics.enabled" value="true"/>
    <property name="application.profile" value="development"/>

    <target name="run">
        <exec executable="java" failonerror="true">
            <!-- Chỉ thêm tham số chẩn đoán khi được bật. -->
            <arg value="-Xlog:gc"
                 if:true="${diagnostics.enabled}"/>

            <!-- Chỉ thêm profile khi đã có giá trị. -->
            <arg value="-Dapplication.profile=${application.profile}"
                 unless:blank="${application.profile}"/>
            <arg value="-jar"/>
            <arg value="build/libs/application.jar"/>
        </exec>
    </target>
</project>
```

`<exec>` vẫn được chạy. Ant chỉ quyết định có đưa từng `<arg>` vào danh sách tham số hay không. Cách này hữu ích khi một task có nhiều tùy chọn nhưng chỉ một vài tùy chọn phụ thuộc vào cấu hình.

Ta cũng có thể đặt điều kiện trực tiếp lên task:

```xml
<echo message="Tạo báo cáo kiểm thử"
      if:set="tests.available"/>
```

Nếu `tests.available` chưa được khai báo, toàn bộ task `<echo>` được bỏ qua. Không cần tạo một target riêng chỉ để bao quanh một task đơn giản.

## 4. Ví dụ tổng hợp

Ví dụ sau kết hợp cả ba loại điều kiện trong một target. Hãy chú ý rằng `debug` có giá trị `false` nhưng vẫn thỏa `if:set`, còn `release.enabled` chỉ thỏa `if:true` khi giá trị của nó là `true`.

```xml
<project name="conditional-build"
         default="package"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="release.enabled" value="true"/>
    <property name="debug" value="false"/>
    <property name="artifact.label" value="application"/>
    <property name="optional.note" value=""/>

    <target name="package">
        <echo message="Bắt đầu đóng gói"/>

        <echo message="Đang tạo bản release"
              if:true="${release.enabled}"/>

        <echo message="Bỏ qua bước release"
              unless:true="${release.enabled}"/>

        <echo message="Cấu hình debug đã được khai báo"
              if:set="debug"/>

        <echo message="Chưa có cấu hình publish"
              unless:set="publish.enabled"/>

        <echo message="Không có ghi chú bổ sung"
              if:blank="${optional.note}"/>

        <echo message="Ghi chú: ${optional.note}"
              unless:blank="${optional.note}"/>

        <echo message="Artifact: ${artifact.label}"
              unless:blank="${artifact.label}"/>
    </target>
</project>
```

Khi chạy target `package`, Ant luôn in thông báo bắt đầu. Vì `release.enabled=true`, thông báo release được in và thông báo bỏ qua release không được in. Vì property `debug` đã được khai báo, thông báo về cấu hình debug vẫn được in dù giá trị của nó là `false`. `publish.enabled` chưa tồn tại nên điều kiện `unless:set` đúng. `optional.note` rỗng nên chỉ thông báo không có ghi chú được in. Cuối cùng, `artifact.label` có nội dung nên thông báo tên artifact được in.

## 5. Phân biệt với `if` và `unless` trên `<target>`

Ant đã hỗ trợ điều kiện ở cấp target từ các phiên bản cũ hơn. Cú pháp này vẫn có mục đích riêng:

```xml
<target name="publish" if="publish.enabled">
    <echo message="Publishing artifact"/>
</target>
```

`if="publish.enabled"` trên `<target>` là điều kiện của target, thường kiểm tra property có tên đó đã được khai báo hay chưa. Nó không giống `if:true="${publish.enabled}"` trên một task: dạng `true` kiểm tra giá trị boolean, còn dạng `set` kiểm tra sự tồn tại của property.

Ngoài ra, điều kiện của target không ngăn các target được liệt kê trong `depends` chạy. Ant thực hiện các dependency trước, rồi mới xét target hiện tại có thỏa `if` hoặc `unless` hay không. Điều kiện namespace trên task giúp kiểm soát trực tiếp một task hoặc phần tử lồng tại nơi nó xuất hiện.

Có thể chọn cách viết theo phạm vi cần kiểm soát:

| Nhu cầu | Cách dùng phù hợp |
|---|---|
| Bỏ qua hoặc chạy toàn bộ một target theo property | `if` / `unless` trên `<target>` |
| Bỏ qua một task theo giá trị boolean | `if:true` / `unless:true` |
| Bỏ qua một task theo sự tồn tại của property | `if:set` / `unless:set` |
| Chỉ thêm một phần tử con khi có hoặc không có nội dung | `if:blank` / `unless:blank` |

## 6. Lỗi thường gặp và cách tránh

1. **Quên khai báo namespace.** Thuộc tính `if:true` hoặc `unless:set` cần prefix đã được khai báo. Đặt `xmlns:if="ant:if"` và `xmlns:unless="ant:unless"` trên `<project>` để dùng xuyên suốt file.
2. **Dùng nhầm `set` và `true`.** Property có giá trị `false` vẫn là property đã được khai báo. Dùng `if:set` nếu cần kiểm tra sự tồn tại; dùng `if:true` nếu cần kiểm tra giá trị bật/tắt.
3. **Đưa property expansion vào `set`.** Viết `if:set="feature.enabled"` vì Ant cần tên property. Với `if:true` hoặc `if:blank`, dùng giá trị sau expansion, chẳng hạn `if:true="${feature.enabled}"`.
4. **Đặt điều kiện sai phạm vi.** Điều kiện trên task cha có thể bỏ qua toàn bộ task và nội dung lồng bên trong. Nếu chỉ muốn bỏ một tham số hoặc một phần tử con, hãy đặt điều kiện lên chính phần tử con đó.
5. **Nhầm điều kiện task với điều kiện target.** `if`/`unless` không namespace trên `<target>` có quy tắc và phạm vi riêng. Không thay `if:true` bằng `if` trên task hoặc ngược lại.
6. **Dùng phiên bản Ant quá cũ.** Namespace điều kiện trên task và phần tử lồng chỉ có từ Ant 1.9.1. Nếu build chạy với Ant cũ hơn, cần nâng phiên bản hoặc dùng cách tổ chức điều kiện tương thích với phiên bản đang chạy.
7. **Dùng cú pháp XML trong Gradle DSL.** `xmlns:if`, `if:true` và `unless:set` là cú pháp của build file XML được Apache Ant phân tích. Khi gọi Ant task từ Gradle Groovy DSL, điều kiện thuộc về cú pháp Groovy/Gradle và không thể chép nguyên các thuộc tính namespace XML này vào lời gọi `ant.*`.

## 7. Quy trình chọn điều kiện

Khi viết một task có điều kiện, hãy xác định chính xác điều cần kiểm tra trước:

1. Nếu cần biết một property có tồn tại hay không, chọn `if:set` hoặc `unless:set` và truyền tên property.
2. Nếu cần biết một cờ đang bật hay tắt, chọn `if:true` hoặc `unless:true` và truyền giá trị property qua `${...}`.
3. Nếu cần biết một giá trị có rỗng hay không, chọn `if:blank` hoặc `unless:blank` và truyền biểu thức cần kiểm tra.
4. Đặt điều kiện lên task nếu muốn bật/tắt toàn bộ hành động; đặt lên phần tử lồng nếu chỉ muốn bật/tắt một thành phần của hành động.
5. Kiểm tra phiên bản Ant thực tế của môi trường build để bảo đảm có hỗ trợ từ 1.9.1.

## Tài liệu tham khảo

- [Apache Ant Manual — If and Unless](https://ant.apache.org/manual/ifunless.html): cú pháp namespace và ba loại điều kiện `true`, `blank`, `set`.
- [Apache Ant Manual — XML Namespace Support](https://ant.apache.org/manual/Types/namespace.html): cách Ant xử lý namespace trên phần tử và thuộc tính.
- [Apache Ant Manual — Properties](https://ant.apache.org/manual/properties.html): ngữ nghĩa điều kiện `if`/`unless` trên target và property expansion.
