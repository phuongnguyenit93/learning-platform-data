# Thời điểm kiểm tra điều kiện sau khi xử lý depends

Trong Apache Ant, một target có thể dùng thuộc tính `if` hoặc `unless` để quyết định có thực hiện các task bên trong target hay không. Một điểm dễ gây nhầm lẫn là thời điểm Ant kiểm tra điều kiện: **Ant thực hiện các target được khai báo trong `depends` trước, rồi mới kiểm tra `if` hoặc `unless` của target hiện tại.**

Điều này cho phép target phụ thuộc chuẩn bị property hoặc kiểm tra trạng thái file, sau đó target phía sau sử dụng kết quả đó để quyết định có chạy phần việc của mình hay không. Đồng thời, nó cũng có nghĩa một target bị bỏ qua vẫn có thể đã làm cho các dependency của nó chạy xong.

## 1. Điều kiện của target hoạt động như thế nào?

Một target có thể khai báo `if` hoặc `unless`:

```xml
<target name="publish" depends="prepare" if="publish.enabled">
    <echo message="Publishing artifact"/>
</target>
```

- `if="publish.enabled"`: Ant chạy các task trong target khi property `publish.enabled` đã được đặt.
- `unless="publish.enabled"`: Ant chạy các task trong target khi property `publish.enabled` chưa được đặt.

Hai thuộc tính này kiểm tra **property có tồn tại hay không**, không phân tích nội dung của property như một giá trị boolean. Nếu property tồn tại với giá trị chuỗi `false`, điều kiện `if` vẫn được xem là đúng; `unless` cũng xem property đó là đã được đặt.

Khi target có `depends`, thứ tự xử lý là:

```text
Gọi target publish
        |
        v
Thực hiện các target trong depends
        |
        v
Kiểm tra if / unless của publish
        |
        +---- Điều kiện đạt ----> Chạy các task trong publish
        |
        +---- Điều kiện không đạt -> Bỏ qua các task trong publish
```

Điều kiện được đánh giá lúc Ant chuẩn bị thực hiện target, sau khi dependency hoàn tất. Ant không kiểm tra điều kiện của `publish` trước rồi mới quyết định có chạy `prepare` hay không.

## 2. Property được dependency thiết lập có thể điều khiển target phía sau

Ví dụ sau có một target chuẩn bị đặt property và một target chỉ thực hiện công việc khi property đó tồn tại:

```xml
<project name="conditional-build" default="publish" basedir=".">
    <target name="prepare">
        <echo message="Preparing publish settings"/>
        <property name="publish.enabled" value="yes"/>
    </target>

    <target name="publish" depends="prepare" if="publish.enabled">
        <echo message="Publishing artifact"/>
    </target>
</project>
```

Chạy:

```bash
ant publish
```

Trình tự xảy ra:

1. Ant bắt đầu xử lý target `publish`.
2. Vì `publish` phụ thuộc `prepare`, Ant thực hiện `prepare` trước.
3. Task `<property>` trong `prepare` đặt property `publish.enabled`.
4. Sau khi dependency hoàn tất, Ant kiểm tra `if="publish.enabled"`.
5. Property đã tồn tại nên Ant thực hiện task `<echo>` của target `publish`.

Nếu target `prepare` không đặt property `publish.enabled`, các task trong `publish` sẽ bị bỏ qua. Đây là cách dùng có chủ đích của việc kiểm tra điều kiện sau dependency: dependency có thể phát hiện hoặc chuẩn bị trạng thái mà target chính cần.

## 3. Dependency vẫn chạy khi target chính bị bỏ qua

Đây là hệ quả quan trọng nhất của thứ tự xử lý trên. Điều kiện `if` hoặc `unless` của một target chỉ quyết định các task thuộc target đó có được thực hiện hay không. Nó không ngăn Ant chạy các target trong `depends`.

Ví dụ:

```xml
<project name="conditional-build" default="publish" basedir=".">
    <target name="prepare">
        <echo message="Preparing files"/>
    </target>

    <target name="publish" depends="prepare" if="publish.enabled">
        <echo message="Publishing artifact"/>
    </target>
</project>
```

Chạy khi property chưa được đặt:

```bash
ant publish
```

Kết quả về mặt luồng thực thi:

```text
Preparing files
publish: skipped because publish.enabled is not set
```

Target `prepare` vẫn chạy và in thông báo. Sau đó Ant kiểm tra điều kiện của `publish`, thấy property chưa tồn tại nên bỏ qua task `echo` trong `publish`.

Vì vậy, không nên đặt một công việc tốn thời gian hoặc có side effect vào dependency của target chỉ với hy vọng điều kiện của target chính sẽ ngăn công việc đó. Nếu cần điều kiện hóa cả chuỗi công việc, phải thiết kế điều kiện cho các target thực sự cần được bỏ qua hoặc tổ chức lại luồng gọi target.

## 4. Dùng condition để kiểm tra giá trị thay vì chỉ kiểm tra sự tồn tại

Thuộc tính `if` của target không có nghĩa là giá trị property phải là `true`. Ví dụ:

```xml
<property name="publish.enabled" value="false"/>

<target name="publish" if="publish.enabled">
    <echo message="Publishing artifact"/>
</target>
```

Target `publish` vẫn chạy vì `publish.enabled` đã được đặt. Ant không chuyển chuỗi `false` thành boolean false khi xử lý thuộc tính `if` cổ điển của target.

Nếu cần kiểm tra giá trị, hãy dùng task `<condition>` để chỉ đặt một property kết quả khi biểu thức đúng:

```xml
<project name="conditional-build" default="publish" basedir=".">
    <property name="environment" value="dev"/>

    <target name="prepare">
        <condition property="publish.enabled">
            <equals arg1="${environment}" arg2="production"/>
        </condition>
    </target>

    <target name="publish" depends="prepare" if="publish.enabled">
        <echo message="Publishing production artifact"/>
    </target>
</project>
```

Chạy với môi trường mặc định:

```bash
ant publish
```

Property `environment` có giá trị `dev`, biểu thức `equals` sai và `publish.enabled` không được tạo. Sau khi target `prepare` kết thúc, điều kiện của `publish` không đạt nên task bên trong bị bỏ qua.

Chạy với môi trường production:

```bash
ant -Denvironment=production publish
```

Property do dòng lệnh truyền vào có sẵn trước khi các target chạy. Trong `prepare`, task `<condition>` so sánh giá trị và đặt `publish.enabled` khi môi trường là `production`. Khi Ant kiểm tra target `publish` sau dependency, property đã tồn tại nên target được thực hiện.

Lưu ý: không dùng `-Dpublish.enabled=false` để biểu diễn trạng thái tắt nếu target đang dùng `if="publish.enabled"`. Property đó vẫn tồn tại. Hãy truyền một giá trị đầu vào như `environment` hoặc `publish.mode`, rồi dùng `<condition>` để tạo property cờ riêng.

## 5. Dùng unless để bỏ qua target khi một property đã được đặt

`unless` là cách viết điều kiện ngược theo sự tồn tại của property. Ví dụ, target `upload` chỉ chạy khi property `skip.upload` chưa tồn tại:

```xml
<target name="upload" depends="package" unless="skip.upload">
    <echo message="Uploading package"/>
</target>
```

Nếu gọi:

```bash
ant upload
```

và `skip.upload` chưa được đặt, Ant chạy các task trong `upload` sau khi `package` hoàn tất.

Nếu gọi:

```bash
ant -Dskip.upload=yes upload
```

Ant vẫn chạy dependency `package` trước. Sau đó property `skip.upload` được phát hiện, vì vậy các task trong target `upload` bị bỏ qua.

| Property `skip.upload` | Kết quả điều kiện `unless` | Task trong `upload` |
|---|---|---|
| Chưa được đặt | Đạt | Được chạy |
| Được đặt thành `yes` | Không đạt | Bị bỏ qua |
| Được đặt thành `false` | Không đạt | Bị bỏ qua |
| Được đặt thành chuỗi rỗng | Không đạt vì property vẫn tồn tại | Bị bỏ qua |

Giá trị cụ thể không quan trọng với `unless` cổ điển; chỉ cần property đã tồn tại là target bị bỏ qua.

## 6. Dùng dependency để phát hiện trạng thái file

Một tình huống thực tế là kiểm tra artifact đã tồn tại hay chưa trước khi thực hiện bước tiếp theo. Task `<available>` có thể đặt property nếu file tồn tại.

```xml
<project name="artifact-flow" default="upload" basedir=".">
    <property name="dist.dir" location="${basedir}/dist"/>
    <property name="artifact.file" location="${dist.dir}/app.jar"/>

    <target name="check-artifact">
        <available file="${artifact.file}" property="artifact.ready"/>
    </target>

    <target name="upload" depends="check-artifact" if="artifact.ready">
        <echo message="Artifact exists. Upload can start."/>
    </target>

    <target name="report-missing" depends="check-artifact" unless="artifact.ready">
        <echo message="Artifact does not exist. Nothing to upload."/>
    </target>
</project>
```

Khi gọi `ant upload`, Ant chạy `check-artifact` trước. Nếu file tồn tại, task `<available>` đặt `artifact.ready`, sau đó target `upload` được thực hiện. Nếu file không tồn tại, target `upload` bị bỏ qua.

Khi gọi `ant report-missing`, cùng dependency được thực hiện trước. Nếu file không tồn tại, `artifact.ready` không được đặt nên target `report-missing` chạy. Trong cùng một lần gọi Ant, property đã được đặt không thể bị xóa hoặc đổi giá trị bằng một lần khai báo property khác; nếu cần kiểm tra trạng thái mới sau khi file thay đổi, hãy chạy một tiến trình build mới hoặc thiết kế lại luồng build để kiểm tra đúng thời điểm.

Ví dụ này cho thấy dependency không chỉ dùng để đảm bảo thứ tự compile/package. Nó còn có thể chuẩn bị thông tin để target phía sau quyết định có thực hiện công việc hay không.

## 7. Điều kiện của một target không điều khiển dependency của nó

Xem đồ thị sau:

```text
deploy (if="deploy.enabled")
   |
   +-- depends: package
                    |
                    +-- depends: test
                                   |
                                   +-- depends: compile
```

Khi gọi `ant deploy`, Ant thực hiện `compile`, rồi `test`, rồi `package`. Chỉ sau khi chuỗi dependency hoàn tất, Ant mới kiểm tra `deploy.enabled` để quyết định có chạy task của `deploy` hay không.

Nếu `deploy.enabled` chưa được đặt, kết quả là phần deploy bị bỏ qua nhưng compile, test và package vẫn đã chạy. Đây không phải lỗi của Ant; đó là ngữ nghĩa được thiết kế của target condition.

Nếu yêu cầu là không chạy cả compile, test và package khi không deploy, hãy xem xét lại đồ thị target. Có thể tách các bước thành hai entry point khác nhau, hoặc dùng một target điều phối không khai báo các bước tốn kém trong `depends` mà chỉ gọi nhánh cần thiết khi điều kiện đã đạt. Khi thiết kế nhánh có điều kiện, cần bảo đảm dependency của từng target vẫn được thực hiện đúng và không vô tình bỏ qua bước bắt buộc.

## 8. Phân biệt điều kiện target và điều kiện task

Điều kiện đặt trên `<target>` quyết định target có chạy các task bên trong sau khi dependency hoàn tất hay không. Đây là chủ đề chính của bài học.

Ant cũng có cơ chế điều kiện ở mức task. Từ Ant 1.9.1, có thể dùng namespace `ant:if` và `ant:unless` cho task để kiểm tra trạng thái property ngay tại task. Ví dụ:

```xml
<project name="task-condition"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">
    <target name="report">
        <echo message="Optional report"
              if:set="report.enabled"/>
        <echo message="Report disabled"
              unless:set="report.enabled"/>
    </target>
</project>
```

Điều kiện task được xét khi task đó được thực thi trong target. Nó không thay đổi thứ tự xử lý dependency của target. Cú pháp namespace và loại điều kiện cần dùng đúng theo phiên bản Ant của dự án; không nhầm cú pháp `if:set` của task với thuộc tính `if="property"` cổ điển trên target.

## 9. Những lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Hành vi thực tế | Cách xử lý |
|---|---|---|
| Target có `if` sai thì dependency không chạy | Dependency chạy trước khi điều kiện của target được kiểm tra | Đưa điều kiện vào đúng target cần bỏ qua hoặc tổ chức lại luồng gọi |
| `if="flag"` kiểm tra flag có giá trị `true` | Nó kiểm tra property có tồn tại | Dùng `<condition>` để so sánh giá trị và chỉ tạo property kết quả khi đúng |
| `unless="flag"` chỉ bỏ qua khi flag có giá trị `true` | Chỉ cần property tồn tại, bất kể giá trị | Dùng property riêng có quy ước rõ ràng |
| Đặt property bên trong target có thể quyết định `if` của chính target đó | Điều kiện target được xét trước khi các task trong target chạy | Đặt property trong dependency hoặc trước khi gọi target |
| Bỏ qua target nghĩa là không có công việc nào được chạy | Các dependency có thể đã chạy xong | Kiểm tra toàn bộ đồ thị dependency khi phân tích side effect |
| Property có thể đổi giá trị ở dependency sau khi đã đặt từ command line | Property Ant bất biến; giá trị đã đặt thường không bị ghi đè | Dùng property đầu vào riêng và tạo property kết quả mới |

## 10. Bài tập thực hành

Tạo một `build.xml` có ba target `prepare`, `publish` và `report`:

1. Trong `prepare`, dùng `<condition>` để đặt `publish.enabled` khi property `environment` bằng `production`.
2. Cho `publish` phụ thuộc `prepare` và dùng `if="publish.enabled"`.
3. Cho `report` phụ thuộc `prepare` và dùng `unless="publish.enabled"`.
4. Chạy `ant publish report` với môi trường mặc định `dev`, ghi lại target nào thực hiện task.
5. Chạy `ant -Denvironment=production publish report` và so sánh kết quả.
6. Thêm một target `expensive-check` vào dependency của `publish`, đặt một `<echo>` trong target đó rồi chạy với môi trường `dev`. Quan sát rằng `expensive-check` vẫn chạy dù task trong `publish` bị bỏ qua.
7. Thử truyền `-Dpublish.enabled=false` và giải thích vì sao `if="publish.enabled"` vẫn đạt.

Sau bài tập, người học cần tự giải thích được thời điểm Ant đánh giá `if`/`unless`, sự khác nhau giữa property tồn tại và property mang giá trị boolean, cũng như ảnh hưởng của điều kiện target lên các task trong dependency graph.

## 11. Ghi nhớ khi thiết kế build

Khi đọc một target có `depends`, hãy lần theo dependency trước, sau đó mới xét điều kiện của target đó. Property do dependency tạo ra có thể được dùng để bật hoặc tắt phần task của target phía sau. Nhưng điều kiện target không phải một công tắc bao quanh toàn bộ dependency graph.

Thiết kế rõ điều này giúp tránh chạy nhầm các bước có side effect, tránh hiểu sai việc build bị bỏ qua và giúp cấu trúc `build.xml` dễ dự đoán hơn. Hãy dùng `depends` để biểu diễn thứ tự bắt buộc; dùng `if`/`unless` để điều khiển phần việc của target theo trạng thái đã được chuẩn bị trước đó.
