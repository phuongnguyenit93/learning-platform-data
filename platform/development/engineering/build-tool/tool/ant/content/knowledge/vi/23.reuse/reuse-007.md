# Khác biệt về tên target, ghi đè và phụ thuộc khi import hoặc include

Khi một dự án Apache Ant có nhiều build file, ta thường muốn tách các target dùng chung ra file riêng rồi đưa chúng vào build chính. Ant có hai cơ chế cấp project là `<import>` và `<include>`. Cả hai đều đọc một build file khác vào cùng project đang chạy, nhưng cách đặt tên target và xử lý quan hệ `depends` khác nhau.

Điểm khác biệt này quyết định build chính có thể ghi đè target dùng chung hay không, target trong file được đưa vào sẽ gọi dependency nào, và có thể đưa cùng một file vào nhiều lần với các tên khác nhau hay không.

## 1. Hai cách tái sử dụng build file

Giả sử dự án có một file `common.xml` chứa các target dùng chung như `init`, `compile` và `package`. Build chính có thể dùng:

```xml
<project name="application" default="build" basedir=".">
    <import file="build-support/common.xml"/>

    <target name="build" depends="package"/>
</project>
```

Hoặc:

```xml
<project name="application" default="build" basedir=".">
    <include file="build-support/common.xml"/>

    <target name="build" depends="common.package"/>
</project>
```

Nếu project trong `common.xml` có tên `common`, hai cách trên có thể tạo ra các tên target khác nhau. `import` giữ tên target gốc để build chính có thể thay thế implementation; `include` luôn đặt target dưới một prefix để giữ các target của file được đưa vào thành một nhóm riêng.

`<import>` có từ Ant 1.6. `<include>` có từ Ant 1.8.0. Các thuộc tính `as` và `prefixSeparator` cũng được hỗ trợ từ Ant 1.8.0. Cả hai phần tử chỉ được khai báo ở cấp project, không đặt bên trong một target.

## 2. Cách import đặt tên target

Khi import một build file, các target trong file đó có thể được tham chiếu bằng tên gốc không có prefix và bằng tên có prefix. Prefix mặc định là giá trị thuộc tính `name` của phần tử `<project>` trong file được import. Có thể thay prefix bằng thuộc tính `as`.

Ví dụ `build-support/common.xml`:

```xml
<project name="common">
    <target name="init">
        <mkdir dir="build"/>
        <echo message="Common init"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Common compile"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Common package"/>
    </target>
</project>
```

Build chính:

```xml
<project name="application" default="build" basedir=".">
    <import file="build-support/common.xml"/>

    <target name="build" depends="common.package"/>
</project>
```

Các target được import có thể truy cập bằng các tên:

| Tên gốc trong `common.xml` | Tên không prefix | Tên có prefix mặc định |
|---|---|---|
| `init` | `init` | `common.init` |
| `compile` | `compile` | `common.compile` |
| `package` | `package` | `common.package` |

Tên không prefix là tên có thể bị target trong build chính ghi đè. Tên có prefix vẫn cho phép gọi implementation ban đầu từ file được import.

## 3. Ghi đè target khi dùng import

Đây là điểm nổi bật của `<import>`. Nếu build chính định nghĩa target có cùng tên với target trong file được import, target của build chính được ưu tiên.

Ví dụ, build chính thay target `init`:

```xml
<project name="application" default="build" basedir=".">
    <import file="build-support/common.xml"/>

    <target name="init">
        <mkdir dir="build/application"/>
        <echo message="Application-specific init"/>
    </target>

    <target name="build" depends="compile"/>
</project>
```

Trong trường hợp này, tên `init` trỏ đến implementation của build chính. Target `common.init` vẫn truy cập được implementation ban đầu trong `common.xml`.

Khi chạy target `compile` được import, dependency của nó vẫn là `init`, vì `import` không viết lại danh sách `depends` trong file được import. Do đó `compile` sẽ gọi target `init` theo tên thông thường, và implementation của build chính được sử dụng.

Luồng thực thi:

```text
application.build
       |
       v
common.compile (được gọi bằng tên compile)
       |
       v
application.init (ghi đè tên init của common)
       |
       v
common.compile tasks
```

Nếu muốn gọi implementation cũ của target `init`, có thể tham chiếu tên prefix `common.init` một cách tường minh. Ví dụ, một target mới có thể phụ thuộc vào `common.init` trước khi thực hiện phần khởi tạo riêng.

Khả năng ghi đè giúp build dùng chung cung cấp một quy trình mặc định, còn dự án cụ thể có thể thay một số bước mà không cần sao chép toàn bộ build file. Đổi lại, cần hiểu rằng dependency không prefix của target được import có thể được chuyển sang implementation mới.

## 4. Prefix khi import bằng thuộc tính as

Thuộc tính `as` đặt prefix tường minh cho các target được import:

```xml
<project name="application" default="build" basedir=".">
    <import file="build-support/common.xml" as="shared"/>

    <target name="build" depends="shared.package"/>
</project>
```

Các alias có prefix bây giờ là `shared.init`, `shared.compile` và `shared.package`. Tên không prefix vẫn được đưa vào project và vẫn có thể bị ghi đè.

Nếu không có target cùng tên trong build chính, tên không prefix cũng có thể gọi target được import. Nếu có target trùng tên, target của build chính được ưu tiên; tên prefix là cách truy cập implementation gốc.

Prefix hữu ích khi tên project trong file dùng chung không phù hợp với cách gọi của dự án, hoặc khi muốn thể hiện rõ vai trò của nhóm target:

```xml
<import file="build-support/java.xml" as="java"/>
<import file="build-support/docs.xml" as="docs"/>
```

Khi đó có thể gọi `java.compile`, `java.jar`, `docs.javadoc` để biểu diễn rõ target thuộc nhóm nào.

## 5. Cách include đặt tên target

Khác với import, `<include>` chỉ công bố target bằng tên có prefix. Prefix mặc định là `name` của project trong file được include; nếu file đó không khai báo tên project, cần cung cấp `as`.

Với `common.xml` ở ví dụ trước:

```xml
<project name="application" default="build" basedir=".">
    <include file="build-support/common.xml"/>

    <target name="build" depends="common.package"/>
</project>
```

Các target chỉ có tên:

```text
common.init
common.compile
common.package
```

Không có target không prefix tên `init`, `compile` hoặc `package` được đưa vào build chính. Vì vậy, build chính không ghi đè được target của file include bằng cách định nghĩa một target cùng tên gốc.

Có thể đổi prefix:

```xml
<include file="build-support/common.xml" as="shared"/>
```

Khi đó các tên target là `shared.init`, `shared.compile` và `shared.package`.

## 6. Include viết lại depends để giữ nhóm target độc lập

Điểm khác biệt quan trọng thứ hai là cách Ant xử lý dependency trong file được đưa vào.

Với `import`, danh sách `depends` giữ nguyên tên gốc. Với `include`, Ant viết lại các tên target trong `depends` bằng cùng prefix của file được include.

Trong `common.xml`:

```xml
<project name="common">
    <target name="init">
        <echo message="Common init"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Common compile"/>
    </target>
</project>
```

Nếu dùng:

```xml
<include file="build-support/common.xml" as="shared"/>
```

Ant tạo quan hệ tương đương:

```text
shared.compile
      |
      v
shared.init
```

Khi chạy `ant shared.compile`, Ant gọi `shared.init` trước. Nếu build chính có target `init`, target đó không thay thế `shared.init`, vì dependency đã được đổi thành tên có prefix.

Nhờ vậy, file include giữ được luồng nội bộ của nó. Người viết file dùng chung kiểm soát target nào được gọi khi một target khác phụ thuộc vào nó.

## 7. Ví dụ so sánh import và include bằng cùng một dependency

Giả sử file `nested.xml`:

```xml
<project name="nested">
    <target name="setUp">
        <property name="build.message" value="value from nested"/>
        <echo message="nested setUp"/>
    </target>

    <target name="show" depends="setUp">
        <echo message="${build.message}"/>
    </target>
</project>
```

### 7.1. Chạy với import

```xml
<project name="main" default="run" basedir=".">
    <import file="nested.xml" as="nested"/>

    <target name="setUp">
        <property name="build.message" value="value from main"/>
        <echo message="main setUp"/>
    </target>

    <target name="run" depends="nested.show"/>
</project>
```

`nested.show` giữ dependency `setUp` không prefix. Target `setUp` của build chính ghi đè target cùng tên được import, nên `main setUp` chạy trước. Property `build.message` nhận giá trị từ main.

### 7.2. Chạy với include

```xml
<project name="main" default="run" basedir=".">
    <include file="nested.xml" as="nested"/>

    <target name="setUp">
        <property name="build.message" value="value from main"/>
        <echo message="main setUp"/>
    </target>

    <target name="run" depends="nested.show"/>
</project>
```

`nested.show` được include thành target có dependency `nested.setUp`. Target `setUp` của main không thay thế dependency đó. Vì thế `nested setUp` chạy và property được đặt theo target trong file nested.

| Cấu hình | Tên target gọi | Dependency bên trong `show` | Target thực hiện |
|---|---|---|---|
| Import | `nested.show` | `setUp` | Target `setUp` của main nếu đã ghi đè |
| Include | `nested.show` | `nested.setUp` | Target `setUp` trong file nested |

Ví dụ này thể hiện rõ sự khác biệt về quyền kiểm soát dependency: import cho phép build chính thay implementation của một bước chung; include giữ nguyên liên kết nội bộ của file được include.

## 8. Bảng so sánh import và include

| Tiêu chí | `<import>` | `<include>` |
|---|---|---|
| Phiên bản Ant | Từ Ant 1.6 | Từ Ant 1.8.0 |
| Tên target được đưa vào | Có tên gốc không prefix và tên có prefix | Chỉ tên có prefix |
| Prefix mặc định | Tên project trong file được đưa vào | Tên project trong file được đưa vào |
| Thuộc tính `as` | Đổi prefix của alias có prefix | Đổi prefix của tất cả target được include |
| Ghi đè target từ file chính | Có; target main cùng tên không prefix được ưu tiên | Không ghi đè bằng tên gốc vì target include chỉ có tên prefix |
| Tên dependency trong file con | Giữ nguyên | Được viết lại thành tên có prefix |
| Khả năng giữ dependency nội bộ độc lập | Không; dependency không prefix có thể được main thay thế | Có; dependency được prefix hóa |
| Đưa cùng một file vào nhiều lần | Không thể import cùng file nhiều lần | Có thể include nhiều lần với prefix khác nhau |
| Mục đích điển hình | Cung cấp target mặc định có thể tùy biến/ghi đè | Đưa một nhóm target tự chứa vào project |

Quy tắc chọn nhanh của tài liệu Ant: dùng `import` nếu muốn ghi đè target; dùng `include` nếu không có nhu cầu ghi đè và muốn giữ dependency nội bộ của file được đưa vào.

## 9. prefixSeparator thay đổi ký tự phân cách

Mặc định, Ant dùng dấu chấm `.` giữa prefix và tên target:

```xml
<include file="build-support/common.xml" as="shared"/>
```

Tên target là `shared.init`, `shared.compile` và `shared.package`.

Có thể đổi dấu phân cách bằng `prefixSeparator`:

```xml
<include file="build-support/common.xml"
         as="shared"
         prefixSeparator="-"/>
```

Tên target trở thành `shared-init`, `shared-compile` và `shared-package`.

Thuộc tính này cũng dùng được với `import`:

```xml
<import file="build-support/common.xml"
        as="shared"
        prefixSeparator="_"/>
```

Khi đó alias có prefix là `shared_init`, `shared_compile`, v.v. Nên giữ một quy ước phân cách nhất quán trong repository; dấu chấm mặc định thường dễ nhận biết và phù hợp với ví dụ trong tài liệu Ant.

## 10. Dùng cùng một file include nhiều lần

Một đặc điểm riêng của include là có thể đưa cùng một build file vào nhiều lần với các prefix khác nhau. Điều này hữu ích khi một nhóm target được tham số hóa bằng property và cần xuất hiện dưới nhiều tên trong cùng project.

Ví dụ:

```xml
<project name="multi-module" default="build-all" basedir=".">
    <include file="build-support/module-targets.xml" as="frontend"/>
    <include file="build-support/module-targets.xml" as="backend"/>

    <target name="build-all" depends="frontend.package,backend.package"/>
</project>
```

Nếu file được include có target `compile` và `package`, Ant tạo:

```text
frontend.compile
frontend.package
backend.compile
backend.package
```

Các dependency nội bộ cũng được prefix theo từng lần include:

```text
frontend.package -> frontend.compile
backend.package  -> backend.compile
```

Không thể dùng `<import>` cùng một file nhiều lần như cách trên. Nếu muốn dùng lại một bộ target theo nhiều namespace độc lập, `include` là lựa chọn phù hợp.

Lưu ý rằng prefix chỉ phân biệt tên target. Property Ant vẫn thuộc cùng project và có tính bất biến; include không tạo một namespace property riêng cho mỗi lần include. Nếu file dùng chung khai báo cùng một property ở cả hai lần include, lần khai báo đầu tiên có thể quyết định giá trị và lần sau không ghi đè được. Cần thiết kế property đầu vào hoặc cấu hình module cẩn thận.

## 11. Import và include là top-level task

Hai phần tử này được xử lý khi Ant đọc build file, không phải task chạy trong một target. Vì vậy không viết:

```xml
<!-- Không hợp lệ: import/include không đặt trong target. -->
<target name="load-common">
    <import file="build-support/common.xml"/>
</target>
```

Hãy đặt chúng trực tiếp bên trong `<project>`:

```xml
<project name="application" default="build">
    <import file="build-support/common.xml"/>

    <target name="build" depends="common.package"/>
</project>
```

Do import/include diễn ra khi parse project, không thể dùng chúng như một nhánh điều kiện được gọi tùy ý trong lúc build đang chạy. Nếu cần chọn build file theo cấu hình, có thể dùng property đã được truyền trước khi Ant đọc build file, chẳng hạn property từ dòng lệnh:

```xml
<import file="build-support/${build.platform}.xml"/>
```

Giá trị property phải có sẵn khi Ant đọc phần tử import. Truyền từ dòng lệnh:

```bash
ant -Dbuild.platform=windows build
```

Không nên dựa vào một task `<property>` nằm trong target để tạo giá trị cho `file`, vì import/include được xử lý trong lúc parse build file, trước khi các target thông thường chạy.

## 12. Đường dẫn file và property ant.file

Với cả import và include, nếu `file` là đường dẫn tương đối, Ant phân giải nó tương đối với file build đang khai báo phần tử import/include. Quy tắc này khác với nhiều thuộc tính đường dẫn khác của Ant vốn thường tính từ `basedir`.

Ví dụ cấu trúc:

```text
workspace/
├── build.xml
└── build-support/
    ├── common.xml
    └── config/
        └── defaults.properties
```

Trong `build.xml`:

```xml
<import file="build-support/common.xml"/>
```

Đường dẫn `build-support/common.xml` được tìm tương đối với file `build.xml`. Bên trong file được import/include, `${basedir}` vẫn gắn với project chính; nó không tự đổi thành thư mục chứa file dùng chung.

Ant cung cấp property đặc biệt `ant.file` cho build file chính và property `ant.file.<project-name>` cho mỗi file được import/include. Phần `<project-name>` lấy từ thuộc tính `name` của phần tử `<project>` trong file đó; nó không đổi theo thuộc tính `as` dùng để đặt prefix target. Có thể dùng property này để xác định vị trí của file build dùng chung và tìm resource đi kèm nó.

Ví dụ, nếu project trong `common.xml` có `name="common"`, kể cả khi file được đưa vào với `as="shared"`:

```xml
<import file="build-support/common.xml" as="shared"/>
<property name="common.config"
          location="${ant.file.common}/../config/defaults.properties"/>
```

Tên property đặc biệt gắn với tên project trong file được đưa vào, còn tên target có prefix gắn với giá trị `as` nếu có. Trong ví dụ trên, target được gọi bằng `shared.init`, nhưng property đường dẫn vẫn là `ant.file.common`. Nếu file không khai báo `name`, property `ant.file.<project-name>` tương ứng sẽ không được đặt; hãy khai báo tên project ổn định nếu cần tham chiếu resource tương đối.

Trong hệ thống build nhiều cấp, đường dẫn tương đối lồng nhau có thể khó theo dõi. Với file cấu hình quan trọng, cân nhắc chuẩn hóa đường dẫn hoặc dùng property dựa trên `ant.file.<project-name>` để tránh phụ thuộc vào thư mục làm việc hiện tại.

## 13. Thuộc tính optional

Mặc định, Ant báo lỗi nếu file import/include không tồn tại. Thuộc tính `optional="true"` cho phép bỏ qua file không có mặt:

```xml
<import file="build-support/local-overrides.xml" optional="true"/>
```

Hoặc:

```xml
<include file="build-support/optional-tools.xml" optional="true"/>
```

Chỉ dùng `optional` cho phần mở rộng thực sự không bắt buộc. Không đặt optional cho file chứa target cốt lõi như compile hoặc package nếu thiếu nó phải được xem là lỗi cấu hình. Nếu bỏ qua một file quan trọng, build có thể tiếp tục nhưng thiếu target cần thiết và chỉ thất bại ở bước xa hơn.

## 14. Extension point: mở rộng quy trình mà không ghi đè target

Ngoài việc ghi đè target qua import, Ant còn có `extension-point` (từ Ant 1.8.0). Extension point là một điểm nối có tên, cho phép build file được import định nghĩa nơi mà build chính có thể bổ sung target.

File dùng chung:

```xml
<project name="java-build">
    <target name="create-layout">
        <mkdir dir="build/classes"/>
    </target>

    <extension-point name="before-compile" depends="create-layout"/>

    <target name="compile" depends="before-compile">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>
</project>
```

Build chính import file và đóng góp một target:

```xml
<project name="application" default="compile" basedir=".">
    <import file="build-support/java-build.xml"/>

    <target name="generate-sources" extensionOf="before-compile">
        <echo message="Generate sources before javac"/>
    </target>
</project>
```

Target `generate-sources` được nối vào extension point `before-compile`. Luồng mong muốn là tạo layout, chạy bước generate-sources rồi compile.

Nếu nhiều target cùng mở rộng một extension point, không nên dựa vào thứ tự tương đối giữa các target mở rộng đó. Nếu một target cần chạy sau target khác, khai báo `depends` rõ ràng. Extension point hữu ích khi file dùng chung muốn công bố những điểm mở rộng hợp lệ mà không yêu cầu build chính thay thế toàn bộ target.

## 15. Cách chọn import hay include trong dự án

Hãy chọn theo quyền kiểm soát mà build chính cần có:

**Dùng import khi:**

- File dùng chung cung cấp implementation mặc định cho các target chuẩn.
- Dự án cần thay thế một target như `compile`, `test` hoặc `package` nhưng vẫn giữ tên target đó.
- Dependency của target được import có thể trỏ đến implementation tùy chỉnh của build chính.
- Cần truy cập implementation gốc bằng alias có prefix để mở rộng hoặc gọi lại.

**Dùng include khi:**

- File được đưa vào là một nhóm target tự chứa.
- Không muốn target trong file chính vô tình thay đổi dependency nội bộ.
- Muốn cùng một file xuất hiện nhiều lần với các prefix khác nhau.
- Muốn tên target thể hiện rõ namespace như `frontend.compile` hoặc `backend.compile`.

Nếu chỉ muốn dùng lại một vài macro, property hoặc path mà không cần đưa target vào project, có thể cân nhắc tách chúng thành file build support khác hoặc dùng cơ chế phù hợp. Import/include chủ yếu giải quyết việc tái sử dụng build file và target.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Target ... does not exist` sau include | Đang gọi tên không prefix | Gọi `prefix.target` theo `as` hoặc tên project |
| Target main không ghi đè được target include | Include chỉ tạo tên target có prefix | Nếu cần override, dùng import hoặc gọi target qua extension point |
| Import gọi nhầm target init | Dependency của target import giữ tên không prefix và main đã override | Dùng alias prefix nếu cần gọi implementation gốc |
| Include chạy dependency khác dự kiến | Chưa nhận ra Ant đã rewrite `depends` | Kiểm tra target prefix hóa và gọi đúng target namespace |
| Import/include không tìm thấy file | Đường dẫn tương đối tính từ file build khai báo import/include | Kiểm tra vị trí file; dùng đường dẫn phù hợp hoặc property |
| Resource trong file dùng chung không tìm thấy | Dùng `${basedir}` với giả định nó là thư mục của file include | Dùng `ant.file.<project-name>` để tham chiếu vị trí file build |
| Import cùng một file nhiều lần gây lỗi | Import không hỗ trợ cùng file nhiều lần | Dùng include với các prefix riêng nếu cần nhiều namespace |
| Hai lần include dùng chung property bị xung đột | Property Ant thuộc cùng project và bất biến | Thiết kế property đầu vào riêng, không kỳ vọng namespace property tự động |
| File tùy chọn bị thiếu nhưng build vẫn chạy thiếu target | Đặt `optional="true"` cho file quan trọng | Chỉ dùng optional với phần mở rộng thật sự không bắt buộc |

## 17. Bài tập thực hành

1. Tạo `common.xml` với target `init`, `compile` và `package`; khai báo dependency theo chuỗi.
2. Import file vào build chính và chạy target bằng tên không prefix lẫn tên có prefix.
3. Định nghĩa target `init` mới trong build chính; quan sát target `compile` được import gọi implementation nào.
4. Gọi alias `common.init` để chạy implementation gốc trong file được import.
5. Thay `import` bằng `include`; cập nhật lệnh gọi sang `common.package` và quan sát dependency được prefix hóa.
6. Định nghĩa target `init` ở build chính khi dùng include; xác nhận nó không thay thế `common.init`.
7. Dùng `as="shared"` và `prefixSeparator="-"`; liệt kê tên target mới.
8. Include cùng một file hai lần với prefix `frontend` và `backend`, rồi gọi hai target package riêng.
9. Thử `optional="true"` với file không tồn tại và so sánh với mặc định.
10. Thêm extension point `before-compile` và một target `generate-sources` dùng `extensionOf`.

Sau bài tập, người học cần tự giải thích được ba điểm: target có tên nào sau khi import/include, target nào có thể ghi đè target khác, và dependency được giữ nguyên hay viết lại theo prefix.

## 18. Ghi nhớ khi tổ chức build dùng chung

`import` và `include` đều giúp chia build thành nhiều file, nhưng chúng thể hiện hai hợp đồng khác nhau. Import phù hợp khi build chính cần quyền thay implementation của target và muốn dependency không prefix đi theo target được ghi đè. Include phù hợp khi file dùng chung cần giữ namespace và dependency nội bộ độc lập.

Hãy đặt tên project và prefix có ý nghĩa, khai báo target dependency rõ ràng, tránh phụ thuộc vào property bất biến giữa nhiều lần include, và dùng extension point khi muốn mở rộng một quy trình mà không thay thế target gốc. Khi hiểu rõ tên target và cách Ant viết lại `depends`, build nhiều file sẽ dễ dự đoán và bảo trì hơn.

## 19. Tài liệu tham khảo

- [Apache Ant Manual: Import Task](https://ant.apache.org/manual/Tasks/import.html)
- [Apache Ant Manual: Include Task](https://ant.apache.org/manual/Tasks/include.html)
- [Apache Ant Manual: Targets and Extension-Points](https://ant.apache.org/manual/targets.html)
