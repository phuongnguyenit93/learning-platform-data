# Điều kiện if và unless trên target

Trong Apache Ant, một `target` gom các task thành một bước của quá trình build. Thuộc tính `depends` xác định những target phải chạy trước; các thuộc tính `if` và `unless` cho phép Ant quyết định có thực thi phần thân của target hiện tại hay không dựa trên trạng thái của property.

Hai thuộc tính này thường được dùng để bật hoặc bỏ qua một bước như kiểm thử tích hợp, đóng gói bản phát hành, tạo tài liệu hoặc chạy một công việc chỉ phù hợp với một môi trường nhất định. Để sử dụng đúng, cần phân biệt việc kiểm tra property có tồn tại với việc kiểm tra giá trị của property, đồng thời hiểu thứ tự Ant xử lý dependency.

## 1. Cú pháp cơ bản

`if` yêu cầu một property phải được thiết lập thì phần thân target mới được thực thi. `unless` yêu cầu property được chỉ định chưa được thiết lập thì phần thân target mới được thực thi.

```xml
<target name="publish" if="release.enabled">
    <echo message="Publishing release" />
</target>

<target name="unit-test" unless="tests.disabled">
    <echo message="Running unit tests" />
</target>
```

Trong ví dụ trên:

- Target `publish` chỉ chạy các task bên trong khi property `release.enabled` đã tồn tại.
- Target `unit-test` chạy các task bên trong khi property `tests.disabled` chưa tồn tại.
- Nếu điều kiện không thỏa mãn, Ant bỏ qua phần thân của target tương ứng.

Có thể dùng đồng thời cả hai thuộc tính:

```xml
<target name="publish" if="release.enabled" unless="release.blocked">
    <echo message="Publishing release" />
</target>
```

Target trên chỉ thực thi khi `release.enabled` đã được thiết lập và `release.blocked` chưa được thiết lập. Nói cách khác, mọi điều kiện được khai báo phải cùng thỏa mãn.

## 2. `if` và `unless` kiểm tra sự tồn tại của property

Điểm quan trọng nhất là Ant kiểm tra property có được thiết lập hay không, chứ không tự phân tích nội dung của giá trị thành boolean.

| Trạng thái property | `if="flag"` | `unless="flag"` |
|---|---|---|
| Property chưa được thiết lập | Không thực thi target | Thực thi target |
| Property được thiết lập với giá trị `true` | Thực thi target | Không thực thi target |
| Property được thiết lập với giá trị `false` | Thực thi target | Không thực thi target |
| Property được thiết lập với giá trị `0` hoặc chuỗi rỗng | Thực thi target | Không thực thi target |

Ví dụ:

```xml
<project name="property-presence" default="demo">
    <property name="feature.enabled" value="false" />

    <target name="demo" if="feature.enabled">
        <echo message="This target still runs" />
    </target>
</project>
```

Mặc dù `feature.enabled` có giá trị là chuỗi `false`, property vẫn đã được thiết lập. Vì vậy, target `demo` vẫn chạy.

Điều này cũng ảnh hưởng tới cách truyền cờ từ command line. Với target:

```xml
<target name="test" unless="skip.tests">
    <echo message="Running tests" />
</target>
```

Lệnh sau sẽ bỏ qua phần thân target:

```shell
ant -Dskip.tests=true test
```

Ngay cả lệnh dưới đây cũng bỏ qua phần thân target:

```shell
ant -Dskip.tests=false test
```

Lý do là cả hai lệnh đều thiết lập property `skip.tests`. Giá trị `false` không làm property trở thành trạng thái chưa thiết lập.

## 3. Dùng task `condition` khi cần kiểm tra giá trị hoặc biểu thức

Nếu muốn quyết định theo giá trị thực tế, chẳng hạn chỉ chạy kiểm thử tích hợp khi `test.mode` bằng `integration`, hãy dùng task `condition` để tạo một property cờ. Sau đó dùng tên property cờ trong `if` hoặc `unless`.

```xml
<project name="conditional-test" default="test">
    <property name="test.mode" value="unit" />

    <condition property="run.integration.tests">
        <equals arg1="${test.mode}" arg2="integration" />
    </condition>

    <target name="test">
        <echo message="Run the regular test build" />
    </target>

    <target name="integration-test" depends="test" if="run.integration.tests">
        <echo message="Run integration tests" />
    </target>
</project>
```

Task `condition` thiết lập `run.integration.tests` khi điều kiện con trả về đúng. Nếu `test.mode` khác `integration`, property cờ không được tạo. Khi đó, target `integration-test` bị bỏ qua.

Có thể chọn chế độ từ command line:

```shell
ant -Dtest.mode=integration integration-test
```

Khi chạy lệnh này, property `test.mode` đã được truyền từ bên ngoài nên giá trị mặc định `unit` trong buildfile không ghi đè nó. Điều kiện `equals` đúng, property `run.integration.tests` được thiết lập và target tích hợp được thực thi.

Task `condition` hỗ trợ nhiều loại điều kiện. Một số loại thường gặp:

| Điều kiện | Ý nghĩa | Ví dụ |
|---|---|---|
| `isset` | Kiểm tra một property đã được thiết lập | `<isset property="release.enabled" />` |
| `equals` | So sánh hai giá trị | `<equals arg1="${test.mode}" arg2="integration" />` |
| `available` | Kiểm tra file, thư mục hoặc resource có sẵn | `<available file="${basedir}/config" type="dir" />` |
| `os` | Kiểm tra hệ điều hành | `<os family="windows" />` |
| `and` | Tất cả điều kiện con đều đúng | `<and>...</and>` |
| `or` | Có ít nhất một điều kiện con đúng | `<or>...</or>` |
| `not` | Phủ định điều kiện con | `<not>...</not>` |

Ví dụ kết hợp nhiều điều kiện:

```xml
<property name="test.mode" value="unit" />

<condition property="run.integration.tests">
    <and>
        <equals arg1="${test.mode}" arg2="integration" />
        <available file="${basedir}/src/integration-test" type="dir" />
    </and>
</condition>

<target name="integration-test" if="run.integration.tests">
    <echo message="Integration test sources are available" />
</target>
```

Target chỉ được thực thi khi chế độ là `integration` và thư mục nguồn kiểm thử tích hợp tồn tại. Nếu một trong hai điều kiện sai, property `run.integration.tests` không được thiết lập.

## 4. Kết hợp với dependency của target

`if` và `unless` chỉ quyết định phần thân của target hiện tại có được thực thi hay không. Các target được khai báo trong `depends` vẫn được xử lý trước khi Ant xét điều kiện của target phụ thuộc.

Ví dụ:

```xml
<target name="prepare">
    <echo message="Preparing build environment" />
</target>

<target name="integration-test" depends="prepare" unless="skip.integration">
    <echo message="Running integration tests" />
</target>
```

Khi chạy:

```shell
ant -Dskip.integration=true integration-test
```

Ant vẫn thực thi target `prepare` trước. Sau đó, Ant thấy `skip.integration` đã được thiết lập nên bỏ qua các task bên trong `integration-test`.

Vì vậy, không nên hiểu `unless` trên một target là công tắc tắt toàn bộ dependency graph của target đó. Nếu muốn bỏ qua một nhánh công việc, hãy đặt điều kiện trên từng target thuộc nhánh cần điều khiển, hoặc thiết kế dependency để các bước dùng chung và các bước tùy chọn được tách rõ ràng.

Ví dụ đặt cùng một cờ trên các bước riêng của nhánh kiểm thử tích hợp:

```xml
<target name="prepare-integration" if="run.integration.tests">
    <echo message="Preparing integration test data" />
</target>

<target name="integration-test"
        depends="prepare-integration"
        if="run.integration.tests">
    <echo message="Running integration tests" />
</target>
```

Khi `run.integration.tests` chưa được thiết lập, phần thân của cả hai target đều bị bỏ qua. Nếu `prepare-integration` còn phụ thuộc vào target khác, các dependency đó vẫn được xử lý theo quy tắc tương tự; cần đặt điều kiện cho từng bước thuộc nhánh tùy chọn nếu muốn bỏ qua phần thân của chúng.

Một dependency dùng chung như `compile` có thể được giữ vô điều kiện nếu các công việc khác cũng cần kết quả biên dịch. Việc target kiểm thử bị bỏ qua không đồng nghĩa với việc biên dịch cũng phải bị bỏ qua.

## 5. Property phải được thiết lập đúng thời điểm

Ant xét điều kiện khi chuẩn bị thực thi target. Vì các dependency được thực thi trước target hiện tại, một dependency có thể thiết lập property mà target phía sau dùng trong `if` hoặc `unless`.

```xml
<target name="detect-platform">
    <condition property="is.windows">
        <os family="windows" />
    </condition>
</target>

<target name="windows-package" depends="detect-platform" if="is.windows">
    <echo message="Creating the Windows package" />
</target>
```

Trình tự xử lý là:

1. Ant chạy `detect-platform` vì đây là dependency của `windows-package`.
2. Task `condition` kiểm tra hệ điều hành và thiết lập `is.windows` nếu đang chạy trên Windows.
3. Ant xét điều kiện của `windows-package`.
4. Nếu `is.windows` đã được thiết lập, phần thân target chạy; nếu chưa, phần thân bị bỏ qua.

Ngược lại, nếu property chỉ được thiết lập trong một target không nằm trên đường dependency đã chạy trước target cần kiểm tra, không thể giả định rằng property đó đã tồn tại. Hãy khai báo quan hệ dependency để thứ tự thiết lập cờ được rõ ràng.

## 6. Property trong Ant có tính chất chỉ thiết lập một lần

Property của Ant về cơ bản là bất biến sau khi được thiết lập. Một lần khai báo sau thường không thay đổi giá trị đã có. Đây là điểm quan trọng khi kết hợp property mặc định, property truyền từ command line và property do `condition` tạo ra.

Ví dụ:

```xml
<property name="test.mode" value="unit" />
```

Nếu người dùng chạy:

```shell
ant -Dtest.mode=integration integration-test
```

Giá trị `integration` từ command line đã tồn tại trước khi buildfile áp dụng giá trị mặc định. Vì property không bị ghi đè, `test.mode` vẫn là `integration`.

Với `condition`, property đích chỉ được thiết lập khi biểu thức đúng. Nếu property đích đã được thiết lập từ trước, task không thể dùng nó để thay đổi trạng thái thành một giá trị khác. Vì vậy:

- Chọn tên property cờ rõ mục đích, ví dụ `run.integration.tests` hoặc `skip.documentation`.
- Không tái sử dụng một property làm cờ cho nhiều điều kiện có ý nghĩa khác nhau.
- Đặt giá trị mặc định ở nơi phù hợp và cho phép người dùng ghi đè bằng `-D` khi cần.
- Nếu cần tính toán trạng thái theo nhiều trường hợp, hãy tạo các property kết quả riêng thay vì cố gắng gán lại cùng một property.

## 7. Ví dụ buildfile hoàn chỉnh

Ví dụ dưới đây mặc định chạy kiểm thử đơn vị. Người dùng có thể chọn chạy kiểm thử tích hợp bằng `-Dtest.mode=integration`. Target tích hợp chỉ chạy khi chế độ phù hợp và thư mục nguồn tích hợp tồn tại.

```xml
<project name="conditional-build" default="build">

    <!-- Giá trị mặc định; có thể được ghi đè bằng -Dtest.mode=... -->
    <property name="test.mode" value="unit" />

    <!-- Chỉ thiết lập cờ khi cả hai điều kiện đều đúng -->
    <condition property="run.integration.tests">
        <and>
            <equals arg1="${test.mode}" arg2="integration" />
            <available file="${basedir}/src/integration-test" type="dir" />
        </and>
    </condition>

    <target name="compile">
        <mkdir dir="build/classes" />
        <echo message="Compile application sources" />
    </target>

    <target name="unit-test" depends="compile" unless="tests.disabled">
        <echo message="Run unit tests" />
    </target>

    <target name="prepare-integration" if="run.integration.tests">
        <echo message="Prepare integration test environment" />
    </target>

    <target name="integration-test"
            depends="compile,prepare-integration"
            if="run.integration.tests">
        <echo message="Run integration tests" />
    </target>

    <target name="build" depends="unit-test,integration-test" />

</project>
```

Một số cách chạy:

```shell
# Chạy build với chế độ mặc định là unit
ant build

# Chọn chế độ integration
ant -Dtest.mode=integration build

# Đặt cờ để bỏ qua phần thân target unit-test
ant -Dtests.disabled=true unit-test
```

Khi chạy `ant build`, `test.mode` có giá trị mặc định là `unit`, do đó `run.integration.tests` không được thiết lập và phần thân của `prepare-integration` cùng `integration-test` bị bỏ qua. Target `compile` vẫn chạy vì là dependency được khai báo.

Khi chạy với `-Dtest.mode=integration`, nếu thư mục nguồn tích hợp tồn tại, điều kiện tạo `run.integration.tests` thành công. Hai target chuẩn bị và kiểm thử tích hợp được thực thi. Nếu thư mục không tồn tại, nhánh tích hợp bị bỏ qua.

Trong ví dụ này, `unit-test` và `integration-test` cùng phụ thuộc vào `compile`. Ant chỉ cần thực thi một lần target `compile` trong cùng một lần build. Cờ `tests.disabled` chỉ điều khiển phần thân `unit-test`; dependency `compile` vẫn chạy.

## 8. Lỗi thường gặp và cách xử lý

| Cách viết hoặc hiện tượng | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| `if="feature.enabled"` nhưng property có giá trị `false` và target vẫn chạy | `if` kiểm tra property có tồn tại hay không | Dùng `condition` để kiểm tra giá trị rồi tạo cờ chỉ được thiết lập khi điều kiện đúng |
| `unless="skip.tests"` nhưng truyền `-Dskip.tests=false` vẫn bỏ qua target | Property đã được thiết lập dù giá trị là `false` | Không dùng chuỗi `false` như trạng thái chưa thiết lập; tạo cờ điều kiện riêng hoặc chỉ truyền property khi muốn bật cờ |
| Viết `if="${feature.enabled}"` | Ant nhận giá trị sau khi thay thế property làm tên property cần kiểm tra; đó không phải cách kiểm tra boolean | Dùng `if="feature.enabled"` nếu chỉ cần kiểm tra sự tồn tại, hoặc dùng `condition` nếu cần so sánh giá trị |
| Target bị bỏ qua nhưng dependency vẫn chạy | Dependency được xử lý trước khi Ant xét `if`/`unless` của target hiện tại | Đặt điều kiện cho từng target trong nhánh tùy chọn hoặc tách dependency dùng chung khỏi nhánh tùy chọn |
| Target không chạy dù điều kiện đáng lẽ đúng | Property cờ chưa được thiết lập tại thời điểm target được xét | Kiểm tra target tạo cờ có nằm trong dependency đã chạy trước đó hay không |
| Giá trị property không thay đổi sau một khai báo mới | Property của Ant chỉ được thiết lập một lần | Chọn tên cờ riêng và xác định nguồn giá trị mặc định/ghi đè ngay từ đầu |
| Điều kiện phức tạp khó đọc khi đặt trong tên target | `if` và `unless` chỉ nhận tên property, không phải biểu thức logic | Tách biểu thức thành task `condition`, sau đó tham chiếu property kết quả |

## 9. Trình tự thiết kế điều kiện cho target

Khi cần thêm điều kiện cho một target, hãy xác định rõ trạng thái nào cho phép bước đó chạy. Sau đó:

1. Quyết định điều kiện chỉ cần kiểm tra property có tồn tại hay phải so sánh giá trị, file, hệ điều hành hoặc nhiều biểu thức.
2. Nếu chỉ kiểm tra sự tồn tại, dùng trực tiếp `if="property.name"` hoặc `unless="property.name"`.
3. Nếu cần biểu thức, dùng task `condition` để thiết lập một property cờ khi biểu thức đúng.
4. Bảo đảm property cờ được thiết lập trước khi Ant xét target, thường bằng cách đặt task tạo cờ ở top-level hoặc trong dependency phù hợp.
5. Kiểm tra dependency graph: điều kiện của target không tự ngăn các dependency chạy.
6. Chạy build với cả trường hợp property được thiết lập và chưa được thiết lập để quan sát hai nhánh.

`if` và `unless` giúp buildfile mô tả các bước có điều kiện bằng property, giữ cho target rõ ràng và dễ tái sử dụng. Khi cần logic phức tạp, task `condition` chịu trách nhiệm tính toán trạng thái; `if` và `unless` chỉ dùng property kết quả để quyết định phần thân target có được thực thi hay không.
