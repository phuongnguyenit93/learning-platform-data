# Chọn nguồn biên dịch bằng `includes`, `excludes` và nhiều thư mục nguồn

Trong một dự án Java, mã nguồn thường được chia thành nhiều nhóm: mã chính, mã được sinh tự động, mã kiểm thử, mã theo từng nền tảng hoặc mã dành riêng cho một sản phẩm. Apache Ant cho phép điều khiển những tệp được đưa vào bước biên dịch bằng task `<javac>`. Các thuộc tính `includes` và `excludes` chọn tệp theo mẫu; thuộc tính `srcdir` hoặc các phần tử lồng `<src>` xác định một hay nhiều thư mục nguồn.

Việc chọn đúng nguồn giúp build chỉ biên dịch phần mã cần thiết, loại bỏ mã thử nghiệm hoặc mã dành cho môi trường khác, và kết hợp được nhiều thư mục nguồn trong cùng một lần gọi compiler.

## 1. Cấu trúc cơ bản của task `<javac>`

Task `<javac>` gọi trình biên dịch Java để biến tệp `.java` thành bytecode `.class`. Một cấu hình cơ bản có dạng:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8"/>
```

Các thuộc tính chính:

- `srcdir`: thư mục hoặc danh sách thư mục chứa mã nguồn Java.
- `destdir`: thư mục nhận các tệp `.class` được biên dịch.
- `includeantruntime`: điều khiển việc đưa thư viện runtime của Ant vào classpath biên dịch; thường đặt `false` để dependency của ứng dụng được khai báo rõ ràng.
- `encoding`: charset dùng để đọc tệp nguồn.
- `includes` và `excludes`: mẫu chọn và loại các tệp nguồn.

Nếu `destdir` chưa tồn tại, nên tạo trước bằng `<mkdir>`:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8"/>
</target>
```

Ant giữ cấu trúc package khi ghi bytecode. Ví dụ, tệp `src/main/java/com/example/Main.java` sẽ tạo lớp `com/example/Main.class` bên dưới `build/classes`.

## 2. Chọn tệp bằng `includes`

`includes` xác định các mẫu tên tệp được phép đưa vào quá trình biên dịch. Mẫu được tính tương đối với từng thư mục nguồn.

Ví dụ chỉ biên dịch các lớp trong package `com.example.service`:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includes="com/example/service/**/*.java"
       includeantruntime="false"/>
```

Mẫu `com/example/service/**/*.java` chọn các tệp Java trong thư mục `service` và các thư mục con của nó. Nếu muốn biên dịch tất cả tệp Java bên dưới thư mục nguồn, có thể dùng:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includes="**/*.java"
       includeantruntime="false"/>
```

Một số wildcard thường dùng:

| Mẫu | Ý nghĩa |
|---|---|
| `*.java` | Tệp Java ngay tại cấp thư mục đang xét |
| `**/*.java` | Tệp Java ở cấp hiện tại và mọi cấp thư mục con |
| `com/example/**/*.java` | Tệp Java trong cây package `com.example` |
| `**/*Service.java` | Tệp có tên kết thúc bằng `Service.java` ở mọi cấp |
| `**/Main.java` | Tệp có tên `Main.java` ở mọi cấp |

Nếu không khai báo include riêng, task `javac` mặc định chọn các tệp nguồn Java theo quy tắc mặc định của nó. Khai báo `includes` tường minh sẽ giúp người đọc thấy rõ phạm vi biên dịch dự kiến.

## 3. Loại trừ tệp bằng `excludes`

`excludes` chỉ định những mẫu không được biên dịch, kể cả khi chúng khớp với mẫu include. Ví dụ, dự án muốn biên dịch toàn bộ mã chính nhưng bỏ qua các lớp thử nghiệm thủ công nằm trong package `sandbox`:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includes="**/*.java"
       excludes="**/sandbox/**,**/*Draft.java"
       includeantruntime="false"/>
```

Trong ví dụ, Ant bỏ qua mọi tệp nằm dưới thư mục `sandbox` và mọi tệp có tên kết thúc bằng `Draft.java`.

Có thể khai báo include/exclude thành các phần tử lồng để dễ đọc hơn:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <include name="**/*.java"/>
    <exclude name="**/sandbox/**"/>
    <exclude name="**/*Draft.java"/>
</javac>
```

Các phần tử `<include>` và `<exclude>` dùng cú pháp mẫu của Ant. Có thể đặt nhiều mẫu để mô tả chính xác nhóm tệp cần biên dịch. Khi một tệp vừa khớp include vừa khớp exclude, mẫu exclude loại tệp đó khỏi tập hợp được chọn.

## 4. Kết hợp nhiều điều kiện include và exclude

Một dự án có thể cần biên dịch các package chính, một số package tiện ích và loại bỏ mã theo nền tảng khác. Ví dụ:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <include name="com/example/core/**/*.java"/>
    <include name="com/example/util/**/*.java"/>
    <include name="com/example/platform/common/**/*.java"/>

    <exclude name="**/internal/**"/>
    <exclude name="**/*Experimental.java"/>
</javac>
```

Các mẫu include xác định những cây package được phép. Các mẫu exclude tiếp tục loại mã nội bộ và mã thử nghiệm khỏi tập hợp. Điều này giúp buildfile thể hiện chính sách chọn nguồn ngay tại nơi định nghĩa target biên dịch.

Khi danh sách mẫu dài, có thể đặt chúng trong tệp include/exclude riêng bằng các thuộc tính tương ứng của task, hoặc dùng datatype `PatternSet` nếu phù hợp với cấu trúc buildfile. Khi đó cần giữ các tệp mẫu cùng repository và tham chiếu bằng đường dẫn ổn định để build có thể chạy trên máy khác.

## 5. Nhiều thư mục nguồn với `srcdir`

Một dự án có thể có nhiều thư mục nguồn cần biên dịch cùng nhau, ví dụ:

```text
project/
├── src/
│   ├── main/java/
│   └── generated/java/
└── build/
    └── classes/
```

Task `javac` hỗ trợ nhiều thư mục nguồn thông qua path trong `srcdir`. Tuy nhiên, chuỗi phân cách path phụ thuộc hệ điều hành. Để buildfile dễ đọc và tránh tự viết dấu phân cách, có thể dùng các phần tử lồng `<src>`:

```xml
<javac destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8">
    <src path="src/main/java"/>
    <src path="src/generated/java"/>
</javac>
```

Ant tìm tệp nguồn ở cả hai thư mục và đưa những tệp phù hợp vào cùng một lần gọi compiler. Mỗi đường dẫn nguồn vẫn là một root riêng; mẫu include/exclude được tính tương đối với root tương ứng.

Nếu dùng thuộc tính `srcdir` với danh sách nhiều đường dẫn, hãy dùng dấu phân cách phù hợp với hệ điều hành hoặc khai báo qua path datatype. Nested `<src>` thường dễ đọc hơn khi buildfile cần hỗ trợ cả Windows, Linux và macOS.

## 6. Nhiều thư mục nguồn và include/exclude

Các điều kiện include/exclude áp dụng cho các nguồn được cung cấp cho cùng task `javac`. Ví dụ dự án có mã chính, mã sinh tự động và một nhóm mã tương thích cũ:

```xml
<javac destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8">
    <src path="src/main/java"/>
    <src path="src/generated/java"/>

    <include name="**/*.java"/>
    <exclude name="**/legacy/**"/>
    <exclude name="**/*Test.java"/>
</javac>
```

Trong cấu hình này, Ant tìm nguồn từ hai root nhưng bỏ qua package `legacy` và các lớp có tên kết thúc bằng `Test.java`. Nếu mã kiểm thử cần được biên dịch riêng, hãy tạo target riêng cho test source và ghi đầu ra vào thư mục khác.

Ví dụ phân chia target main và test:

```xml
<project name="multi-source-build" default="compile" basedir=".">

    <property name="main.classes" location="build/classes"/>
    <property name="test.classes" location="build/test-classes"/>

    <target name="compile">
        <mkdir dir="${main.classes}"/>
        <javac destdir="${main.classes}"
               includeantruntime="false"
               encoding="UTF-8">
            <src path="src/main/java"/>
            <src path="src/generated/java"/>
            <include name="**/*.java"/>
            <exclude name="**/experimental/**"/>
        </javac>
    </target>

    <target name="compile-test" depends="compile">
        <mkdir dir="${test.classes}"/>
        <javac srcdir="src/test/java"
               destdir="${test.classes}"
               includeantruntime="false"
               encoding="UTF-8">
            <include name="**/*.java"/>
            <classpath>
                <pathelement location="${main.classes}"/>
            </classpath>
        </javac>
    </target>

</project>
```

Target `compile-test` phụ thuộc `compile`, nên mã chính được biên dịch trước. Mã kiểm thử được ghi vào `build/test-classes` và có thể tham chiếu các lớp chính thông qua classpath. Thư viện kiểm thử như JUnit cần được bổ sung vào classpath của target test nếu mã nguồn sử dụng chúng.

## 7. Phân biệt `srcdir` và `sourcepath`

Hai khái niệm này có liên quan nhưng không đồng nghĩa:

- `srcdir` xác định các thư mục nguồn mà task Ant quét để chọn tệp đưa vào lời gọi biên dịch.
- `sourcepath` là đường dẫn nguồn mà compiler dùng để tìm thêm mã nguồn khi cần phân giải kiểu hoặc dependency nguồn.

Ví dụ có thể khai báo riêng:

```xml
<javac srcdir="src/main/java"
       sourcepath="src/shared/java"
       destdir="build/classes"
       includeantruntime="false">
    <include name="**/*.java"/>
</javac>
```

Trong trường hợp này, `src/main/java` là nguồn được Ant quét theo mẫu. `src/shared/java` được cung cấp làm source path cho compiler. Tùy compiler, cấu hình sourcepath và các tùy chọn biên dịch, compiler có thể tìm và biên dịch thêm nguồn được tham chiếu gián tiếp. Nếu muốn kiểm soát chặt danh sách tệp được biên dịch, cần hiểu rõ vai trò sourcepath và không coi nó đơn giản là một include root khác.

Nếu không khai báo `sourcepath`, Ant thường dùng các thư mục nguồn đã chỉ định làm source path mặc định cho compiler. Hãy xem tài liệu task và compiler đang sử dụng nếu dự án phụ thuộc vào hành vi biên dịch nguồn gián tiếp.

## 8. Mẫu include/exclude và cấu trúc package

Mẫu include/exclude được viết theo đường dẫn tương đối bên dưới mỗi source root, không phải tên package Java có dấu chấm. Ví dụ:

```text
src/main/java/
└── com/
    └── example/
        ├── api/
        │   └── InventoryService.java
        ├── internal/
        │   └── CacheStore.java
        └── model/
            └── Item.java
```

Muốn chọn package `api` và `model` nhưng bỏ `internal`, có thể viết:

```xml
<javac srcdir="src/main/java" destdir="build/classes">
    <include name="com/example/api/**/*.java"/>
    <include name="com/example/model/**/*.java"/>
    <exclude name="com/example/internal/**"/>
</javac>
```

Không viết mẫu `com.example.api.*` theo cú pháp package Java; Ant sử dụng mẫu đường dẫn với dấu gạch chéo `/`.

Khi có nhiều source root, cùng một đường dẫn tương đối có thể xuất hiện ở nhiều root. Cần tránh hai tệp cùng khai báo một fully qualified class name, vì compiler có thể báo trùng lớp hoặc kết quả phụ thuộc nguồn được tìm thấy. Mỗi lớp Java nên có một nguồn có thẩm quyền trong tập hợp được biên dịch.

## 9. Sử dụng tệp mẫu include/exclude

Khi danh sách nguồn dài, có thể lưu mẫu trong tệp riêng và tham chiếu bằng `includesfile` hoặc `excludesfile`:

`config/java-includes.txt`:

```text
com/example/api/**/*.java
com/example/model/**/*.java
com/example/util/**/*.java
```

`config/java-excludes.txt`:

```text
**/internal/**
**/*Experimental.java
```

Buildfile:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includesfile="config/java-includes.txt"
       excludesfile="config/java-excludes.txt"
       includeantruntime="false"/>
```

Mỗi dòng trong tệp mẫu là một pattern. Cách này hữu ích khi nhiều target cần dùng cùng chính sách chọn nguồn hoặc khi danh sách include/exclude được quản lý riêng. Hãy bảo đảm đường dẫn tới các tệp pattern được tính từ đúng thư mục cơ sở của project.

## 10. Ví dụ buildfile nhiều source root theo module

Một dự án có thể kết hợp mã chính, mã được sinh và mã theo nền tảng. Ví dụ:

```xml
<project name="platform-application" default="compile" basedir=".">

    <property name="classes.dir" location="build/classes"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>

        <javac destdir="${classes.dir}"
               release="17"
               includeantruntime="false"
               encoding="UTF-8">
            <src path="src/main/java"/>
            <src path="src/generated/java"/>
            <src path="src/platform/common/java"/>

            <include name="**/*.java"/>
            <exclude name="**/experimental/**"/>
            <exclude name="**/platform/android/**"/>
        </javac>
    </target>

</project>
```

Target này biên dịch nguồn chính, nguồn sinh tự động và phần dùng chung của nền tảng. Mã thử nghiệm và mã dành riêng cho Android không được đưa vào lần biên dịch này. Nếu cần build cho Android, có thể tạo target khác với tập hợp source root và exclude tương ứng.

## 11. Tính gia tăng và việc chọn nguồn

Task `javac` thường hỗ trợ biên dịch gia tăng dựa trên thời điểm sửa đổi của nguồn và tệp class tương ứng. Việc chọn nguồn bằng include/exclude quyết định những tệp nào đủ điều kiện được xét. Nó không tự xóa các `.class` cũ được tạo từ một tệp đã bị loại khỏi pattern ở lần build mới.

Ví dụ, nếu một lớp từng được biên dịch nhưng sau đó bị loại bằng `excludes`, tệp `.class` cũ có thể vẫn còn trong `destdir`. Nếu build cần đầu ra sạch và phản ánh chính xác tập nguồn hiện tại, hãy cân nhắc target `clean` xóa thư mục build trước khi biên dịch:

```xml
<target name="clean">
    <delete dir="build/classes"/>
</target>

<target name="compile" depends="clean">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includes="**/*.java"
           excludes="**/experimental/**"
           includeantruntime="false"/>
</target>
```

Không phải build nào cũng cần xóa đầu ra trước mỗi lần biên dịch; việc clean làm mất lợi ích của incremental compile. Chọn chiến lược phù hợp với yêu cầu tái lập đầu ra và thời gian build của dự án.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có tệp nào được biên dịch | Pattern include không khớp đường dẫn tương đối hoặc source root sai | Kiểm tra `srcdir`, nested `<src>` và mẫu include dùng dấu `/` |
| Một package không được biên dịch | Package bị loại bởi exclude hoặc chưa được include | Xem lại các mẫu include/exclude và thứ tự phạm vi chọn |
| Tệp test bị biên dịch cùng mã chính | Pattern `**/*.java` bao gồm cả test source trong cùng source root | Tách test source root hoặc loại bằng `**/*Test.java` và thư mục test |
| Nguồn sinh tự động không được tìm thấy | Chưa thêm thư mục generated vào `srcdir`/nested `<src>` | Bổ sung source root sau khi task sinh mã đã chạy |
| Compiler báo duplicate class | Hai source root chứa cùng fully qualified class hoặc một lớp bị chọn nhiều lần | Loại nguồn trùng và xác định một source root có thẩm quyền |
| Lớp cũ vẫn xuất hiện sau khi exclude nguồn | `.class` cũ còn trong `destdir` từ lần build trước | Clean đầu ra khi cần build sạch hoặc xóa riêng artifact không còn hợp lệ |
| Đường dẫn nhiều source root chạy trên Windows nhưng lỗi trên Linux | Tự ghép chuỗi `srcdir` bằng dấu phân cách không phù hợp | Dùng nested `<src>` hoặc datatype `Path` để Ant xử lý path |
| Compiler tìm thấy nguồn ngoài danh sách include | `sourcepath` cho phép compiler tìm nguồn tham chiếu bổ sung | Kiểm tra và cấu hình riêng `sourcepath` nếu cần kiểm soát chặt nguồn |

## 13. Checklist chọn nguồn cho `<javac>`

- [ ] Mỗi source root cần biên dịch đã được khai báo bằng `srcdir` hoặc nested `<src>`.
- [ ] Các pattern include dùng đường dẫn tương đối với source root và dấu `/`.
- [ ] Các pattern exclude loại đúng mã thử nghiệm, mã nội bộ hoặc mã nền tảng không cần thiết.
- [ ] Các tệp được chọn đều thuộc đúng tập nguồn của target.
- [ ] Mã chính và mã kiểm thử được tách riêng khi có yêu cầu biên dịch khác nhau.
- [ ] Nguồn sinh tự động chỉ được biên dịch sau khi task tạo nguồn đã hoàn tất.
- [ ] Không có hai nguồn cùng khai báo một fully qualified class name.
- [ ] `sourcepath` được phân biệt với danh sách tệp do `srcdir` và include/exclude chọn.
- [ ] Đã quyết định có cần clean `destdir` khi tập nguồn thay đổi hay không.
- [ ] Đường dẫn nhiều source root hoạt động trên các hệ điều hành mục tiêu.

`includes` và `excludes` xác định tệp Java nào được chọn; `srcdir` và nested `<src>` xác định nơi Ant tìm nguồn. Kết hợp các cơ chế này giúp buildfile biên dịch đúng phần mã cần thiết, hỗ trợ nhiều source root và giữ ranh giới rõ ràng giữa mã chính, mã sinh tự động, mã kiểm thử và mã dành riêng cho từng nền tảng.
