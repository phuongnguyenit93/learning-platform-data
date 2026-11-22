# Hành vi chạy lặp khi gọi nhiều target hoặc tạo lần chạy Ant mới

Trong một buildfile, nhiều target thường dùng chung các bước chuẩn bị. Chẳng hạn `compile-api` và `compile-web` đều cần target `prepare` tạo thư mục đầu ra. Khi gọi cả hai target trong cùng một lần chạy Ant, bước chuẩn bị dùng chung chỉ cần thực hiện một lần. Nhưng nếu chạy Ant thêm một lần nữa, Ant bắt đầu một lượt build mới và các target cần thiết sẽ được thực hiện lại.

Hiểu rõ phạm vi của một lần chạy giúp tránh nhầm lẫn giữa hai tình huống: target được nhiều nhánh phụ thuộc cùng tham chiếu trong một build, và target được gọi lại trong một tiến trình Ant mới.

## 1. Một target chỉ được thực hiện một lần trong cùng một lần chạy project

Ant tổ chức các target theo quan hệ phụ thuộc. Khi một target cần target khác chạy trước, khai báo `depends` mô tả mối quan hệ đó.

Ví dụ:

```xml
<project name="shared-targets" default="build-all" basedir=".">

    <target name="prepare">
        <echo message="Preparing output directories"/>
        <mkdir dir="build"/>
    </target>

    <target name="compile-api" depends="prepare">
        <echo message="Compiling API"/>
    </target>

    <target name="compile-web" depends="prepare">
        <echo message="Compiling Web"/>
    </target>

    <target name="build-all" depends="compile-api,compile-web">
        <echo message="Build completed"/>
    </target>

</project>
```

Đồ thị phụ thuộc có dạng:

```text
                  build-all
                  /       \
                 /         \
          compile-api    compile-web
                 \         /
                  \       /
                   prepare
```

Khi chạy:

```sh
ant build-all
```

Ant cần thực hiện `prepare` trước `compile-api` và `compile-web`. Dù `prepare` được tham chiếu từ hai nhánh, target này chỉ được thực hiện một lần trong lượt build hiện tại. Khi Ant đi tới nhánh thứ hai, nó nhận biết `prepare` đã được xử lý và không chạy lại phần thân target đó.

Đây là quy tắc chung: trong cùng một project execution, mỗi target được thực hiện tối đa một lần, kể cả khi nhiều target phụ thuộc cùng cần nó.

## 2. Gọi nhiều target trên cùng một dòng lệnh

Ant cho phép truyền nhiều tên target trong một lần gọi:

```sh
ant compile-api compile-web
```

Với buildfile ở phần trước, thứ tự xử lý là:

1. Ant xử lý prerequisite `prepare` của `compile-api`.
2. Ant thực hiện `compile-api`.
3. Ant xử lý prerequisite `prepare` của `compile-web`; target này đã chạy nên được bỏ qua.
4. Ant thực hiện `compile-web`.

Vì vậy, thông điệp `Preparing output directories` chỉ xuất hiện một lần trong log của lệnh trên.

Điều tương tự xảy ra nếu cùng một target được yêu cầu trực tiếp nhiều lần trong danh sách:

```sh
ant prepare compile-api prepare compile-web
```

Trong cùng lượt chạy, target `prepare` không được thực hiện lại ở vị trí thứ ba. Ant ghi nhận target đã hoàn thành trong project execution hiện tại.

Các target được truyền trên dòng lệnh được xử lý theo thứ tự yêu cầu, đồng thời vẫn tuân thủ prerequisite của từng target. Nếu target thứ hai cần một target đã được chạy bởi target thứ nhất, prerequisite dùng chung đó không chạy lần nữa.

## 3. Tạo một lần chạy Ant mới sẽ thực hiện target lại

Quy tắc chạy một lần chỉ áp dụng trong phạm vi một project execution. Mỗi lệnh `ant` chạy riêng tạo một lượt build mới với trạng thái thực thi target mới.

Ví dụ, chạy hai lệnh sau trong hai lần gọi terminal riêng:

```sh
ant compile-api
ant compile-web
```

Lần thứ nhất:

- Ant thực hiện `prepare`.
- Ant thực hiện `compile-api`.
- Lượt build kết thúc.

Lần thứ hai:

- Ant khởi tạo lượt build mới.
- Target `prepare` được thực hiện lại vì trạng thái target của lần chạy trước không được giữ để tái sử dụng.
- Ant thực hiện `compile-web`.

Do đó, thông điệp `Preparing output directories` xuất hiện trong cả hai lần gọi. Việc `prepare` đã chạy ở tiến trình Ant trước không khiến Ant tự bỏ qua target trong tiến trình mới.

Ant không tự lưu một danh sách target đã chạy giữa các lần gọi dòng lệnh để quyết định bỏ qua target ở lần sau. Nếu muốn bỏ qua công việc đã hoàn tất từ một lượt build trước, cần dùng cơ chế kiểm tra trạng thái đầu ra hoặc khả năng incremental của task cụ thể.

## 4. So sánh các tình huống gọi target

| Tình huống | Target dùng chung có chạy lại không? | Lý do |
|---|---|---|
| Một target phụ thuộc được nhiều nhánh tham chiếu trong cùng lượt build | Không | Ant chỉ thực hiện target một lần trong project execution |
| Gọi hai target trên cùng dòng lệnh, có prerequisite chung | Không | Prerequisite đã chạy ở target trước được tái sử dụng trong cùng lượt |
| Gọi cùng tên target hai lần trong danh sách target của một lệnh | Không | Target đã được đánh dấu thực hiện trong lượt hiện tại |
| Chạy cùng lệnh `ant` ở hai lần gọi riêng | Có | Mỗi lần gọi tạo trạng thái thực thi mới |
| Chạy target thông qua một lời gọi `antcall` | Có thể | `antcall` thực thi target trong project context riêng |

Điểm quan trọng là phải xác định ranh giới lượt chạy. Hai target được gọi liên tiếp trên cùng lệnh không giống hai lệnh Ant riêng biệt.

## 5. Phân biệt việc chạy lại target với việc chạy lại task

Một target là nhóm task. Khi target được thực hiện, các task bên trong target được xử lý theo thứ tự khai báo. Nếu target không được thực hiện lại trong cùng lượt build, các task của nó cũng không tự chạy lại chỉ vì một nhánh khác tham chiếu target đó.

Ví dụ:

```xml
<target name="prepare">
    <echo message="Prepare task runs"/>
    <mkdir dir="build"/>
    <echo message="Prepare finished"/>
</target>
```

Nếu hai target khác nhau cùng phụ thuộc `prepare`, các task `echo` trong `prepare` chỉ chạy một lần trong cùng lượt Ant. Khi tạo lượt Ant mới, chúng chạy lại.

Tuy nhiên, việc một task được gọi lại không đồng nghĩa lúc nào nó cũng thay đổi tệp. Nhiều task Ant có logic riêng để tránh thao tác không cần thiết. Ví dụ, task sao chép có thể bỏ qua tệp đích đã mới hơn nguồn theo quy tắc timestamp mặc định; task biên dịch Java có thể chỉ biên dịch những nguồn cần cập nhật.

Vì vậy, cần phân biệt:

- **Target execution:** Ant có thực hiện target trong lượt build hiện tại hay không.
- **Task execution:** Các task bên trong target có được gọi hay không.
- **Task work:** Khi được gọi, task có thực sự ghi lại tệp hoặc thực hiện thay đổi hay tự nhận thấy đầu ra đã cập nhật.

Ant có thể gọi target và task trong một lượt mới, trong khi task cụ thể vẫn không phải ghi lại mọi đầu ra nếu dữ liệu đã mới.

## 6. Target không tự động trở thành incremental giữa các lần chạy

Giả sử target `generate-report` chứa một task tạo báo cáo. Sau khi chạy thành công, lần gọi Ant tiếp theo vẫn thực hiện target đó nếu target được yêu cầu hoặc là prerequisite của target được yêu cầu.

```xml
<target name="generate-report">
    <echo message="Generating report"/>
    <!-- Các task tạo báo cáo đặt ở đây. -->
</target>
```

Ant không suy luận rằng báo cáo vẫn còn mới chỉ vì target đã chạy thành công lần trước. Nếu muốn tránh tạo lại báo cáo khi đầu vào không thay đổi, buildfile phải mô tả điều kiện đó bằng các task kiểm tra như `<uptodate>`, `<available>`, `<condition>` hoặc cơ chế incremental của task phù hợp.

Ví dụ đơn giản, dùng `<uptodate>` để đặt property khi tệp đầu ra đã mới hơn tệp nguồn:

```xml
<project name="incremental-example" default="build" basedir=".">

    <property name="src.file" location="src/input.txt"/>
    <property name="output.file" location="build/output.txt"/>

    <target name="check-output">
        <uptodate property="output.current"
                  targetfile="${output.file}"
                  srcfile="${src.file}"/>
    </target>

    <target name="generate" depends="check-output" unless="output.current">
        <mkdir dir="build"/>
        <copy file="${src.file}" tofile="${output.file}"/>
        <echo message="Output generated"/>
    </target>

    <target name="build" depends="generate"/>

</project>
```

Trong ví dụ, target `check-output` kiểm tra quan hệ thời gian giữa nguồn và đầu ra. Nếu đầu ra tồn tại và mới hơn nguồn, task `<uptodate>` đặt property `output.current`. Thuộc tính `unless` trên target `generate` khiến phần thân target được bỏ qua khi property đó đã được đặt.

Lưu ý rằng target prerequisite vẫn được xử lý trước khi điều kiện `if` hoặc `unless` quyết định có thực hiện phần thân target hay không. Điều kiện trên target không ngăn Ant chạy các dependency của target đó.

Đây là một ví dụ minh họa cách tạo quyết định dựa trên trạng thái tệp. Với build thực tế, hãy chọn điều kiện và task phù hợp với loại đầu vào, đầu ra, nhiều nguồn và yêu cầu xóa/cập nhật dữ liệu của dự án.

## 7. `antcall` và việc gọi target trong project context khác

Ngoài quan hệ `depends`, Ant có task `<antcall>` để gọi một target khác trong cùng buildfile:

```xml
<project name="antcall-example" default="main" basedir=".">

    <target name="prepare">
        <echo message="Prepare target executed"/>
    </target>

    <target name="main">
        <antcall target="prepare"/>
        <antcall target="prepare"/>
    </target>

</project>
```

`antcall` chạy target được chỉ định trong một project context riêng. Vì mỗi lời gọi tạo ngữ cảnh thực thi riêng, target `prepare` có thể được thực hiện lại ở mỗi lần gọi `antcall`, kể cả khi nó đã được thực hiện trong project context của build chính.

Không nên dùng `<antcall>` chỉ để biểu diễn prerequisite thông thường. Với quan hệ phụ thuộc giữa các target, hãy ưu tiên `depends`:

```xml
<target name="prepare">
    <mkdir dir="build"/>
</target>

<target name="compile" depends="prepare">
    <echo message="Compile after prepare"/>
</target>
```

`depends` cho Ant biết các target thuộc cùng đồ thị thực thi và cho phép dùng chung prerequisite chỉ một lần trong lượt build. `antcall` phù hợp với những tình huống cần gọi target trong project context riêng, nhưng làm luồng thực thi phức tạp hơn và có quy tắc truyền property riêng.

## 8. Những tác dụng phụ cần cân nhắc khi target chạy lại

Vì target sẽ được thực hiện trong mỗi lượt Ant mới, hãy xem xét các task có tác dụng phụ:

- `<mkdir>` có thể chạy lại an toàn nếu đường dẫn đã là thư mục.
- `<echo>` sẽ in thông điệp lại mỗi lần target được thực hiện.
- `<copy>` hoặc `<move>` có thể thay đổi tệp tùy thuộc tùy chọn và trạng thái nguồn/đích.
- `<delete>` có thể xóa dữ liệu nếu target được gọi lại.
- Task chạy script hoặc gọi chương trình ngoài có thể lặp lại thao tác bên ngoài Ant.
- Task tải dữ liệu hoặc gọi dịch vụ từ xa có thể gửi yêu cầu lại ở mỗi lần chạy.

Không nên dựa vào việc target chỉ chạy một lần trong lịch sử dự án. Quy tắc chỉ chạy một lần giới hạn trong một project execution; lần chạy mới có thể lặp lại mọi tác dụng phụ của target.

Nếu target có thao tác không nên lặp lại, hãy bổ sung điều kiện kiểm tra trạng thái, thiết kế thao tác có thể chạy lặp an toàn hoặc tách riêng bước cần kiểm soát. Với các thao tác có hậu quả bên ngoài, cần xác định rõ điều kiện chạy trước khi đưa vào target mặc định.

## 9. Quan sát số lần target được thực hiện

Task `<echo>` là cách đơn giản để quan sát target nào được thực hiện và bao nhiêu lần:

```xml
<project name="execution-count" default="all" basedir=".">

    <target name="common">
        <echo message="COMMON TARGET"/>
    </target>

    <target name="first" depends="common">
        <echo message="FIRST TARGET"/>
    </target>

    <target name="second" depends="common">
        <echo message="SECOND TARGET"/>
    </target>

    <target name="all" depends="first,second"/>

</project>
```

Thử lần lượt:

```sh
ant all
ant first second
ant first
ant second
```

Quan sát số lần xuất hiện của `COMMON TARGET`:

- Trong `ant all`, thông điệp xuất hiện một lần dù cả `first` và `second` cùng phụ thuộc `common`.
- Trong `ant first second`, thông điệp cũng xuất hiện một lần vì hai target được gọi trong cùng lượt Ant.
- Trong `ant first` rồi `ant second` bằng hai lệnh riêng, thông điệp xuất hiện một lần trong mỗi lệnh vì mỗi lệnh là một lượt mới.

Có thể tăng mức chi tiết của log bằng:

```sh
ant -verbose all
```

Khi cần kiểm tra target được chọn, dependency nào được xử lý và target nào bị bỏ qua do đã chạy, log chi tiết sẽ giúp lần theo thứ tự thực thi.

## 10. Lỗi hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân | Cách hiểu hoặc xử lý |
|---|---|---|
| Target chuẩn bị chạy một lần dù có hai nhánh phụ thuộc | Ant chỉ thực hiện target một lần trong cùng project execution | Đây là hành vi dự kiến; dùng `depends` để chia sẻ prerequisite |
| Target chuẩn bị chạy lại khi gọi lệnh Ant thứ hai | Lệnh mới tạo project execution mới | Nếu cần bỏ qua công việc cũ, thêm cơ chế kiểm tra đầu ra hoặc incremental |
| Gọi target hai lần trên cùng dòng lệnh nhưng task không chạy lần hai | Target đã được thực hiện trong lượt hiện tại | Muốn thực hiện trong ngữ cảnh riêng, cân nhắc `antcall` khi thực sự cần |
| Target chạy lại nhưng tệp đầu ra không thay đổi | Task có thể tự bỏ qua thao tác khi đầu ra đã mới | Phân biệt target được thực hiện với task có ghi lại tệp hay không |
| Target bị thực hiện lại và lặp tác dụng phụ | Build mới thực hiện target lại | Thiết kế task chạy lặp an toàn hoặc kiểm tra điều kiện trước khi thao tác |
| Dùng `antcall` khiến property hoặc thứ tự thực thi khó hiểu | `antcall` tạo project context riêng và có quy tắc truyền property | Ưu tiên `depends` cho quan hệ prerequisite thông thường |

## 11. Checklist khi thiết kế target dùng chung

- [ ] Đã xác định target nào là prerequisite dùng chung của nhiều nhánh.
- [ ] Đã khai báo quan hệ `depends` đúng với các bước thực sự cần chạy trước.
- [ ] Hiểu rằng target dùng chung chỉ chạy một lần trong cùng project execution.
- [ ] Hiểu rằng một lệnh Ant mới sẽ có trạng thái thực thi target mới.
- [ ] Không nhầm việc target chạy lại với việc task chắc chắn ghi lại mọi tệp đầu ra.
- [ ] Đã bổ sung kiểm tra trạng thái hoặc incremental behavior nếu muốn bỏ qua công việc đã cập nhật ở lượt trước.
- [ ] Đã xem xét tác dụng phụ khi target được gọi lại ở lần build tiếp theo.
- [ ] Chỉ dùng `antcall` khi cần project context riêng, không dùng thay cho `depends` thông thường.

Khi phân biệt đúng phạm vi của một lần chạy Ant, ta có thể thiết kế target dùng chung rõ ràng, tránh thực hiện lặp không cần thiết trong cùng build và chủ động kiểm soát công việc cần lặp lại ở những lần build tiếp theo.
