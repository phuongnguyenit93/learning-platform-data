# Thiết kế macro có đầu vào rõ ràng và property cục bộ

Apache Ant cho phép đóng gói một chuỗi task thường dùng thành một macro bằng **macrodef**. Macro giúp build file tránh lặp lại cùng một đoạn XML khi nhiều module cần thực hiện quy trình tương tự, chẳng hạn tạo thư mục, copy resource, biên dịch hoặc chạy kiểm tra.

Một macro dễ tái sử dụng cần có giao diện rõ ràng: những giá trị nào người gọi phải truyền, giá trị nào có mặc định, những task con nào người gọi được chèn vào và dữ liệu tạm nào chỉ nên tồn tại trong một lần gọi. Hai cơ chế hỗ trợ trực tiếp việc đó là:

- **attribute** và **element** của macrodef định nghĩa đầu vào của macro.
- **local** khai báo property trong phạm vi target hoặc khối sequential, giúp mỗi lần gọi macro có thể dùng tên property tạm giống nhau mà không làm nhiễm không gian property toàn project.

## 1. Macro là gì và khi nào nên dùng?

Macro là một task do người viết build file định nghĩa bằng task **macrodef**. Macrodef dùng một phần tử **sequential** làm mẫu; khi macro được gọi, Ant thay các tham số trong mẫu rồi thực thi chuỗi task đó.

Ví dụ đơn giản:

~~~xml
<macrodef name="say-hello">
    <attribute name="name"/>
    <sequential>
        <echo message="Hello, @{name}!"/>
    </sequential>
</macrodef>
~~~

Sau khi định nghĩa, có thể gọi macro như một task Ant:

~~~xml
<say-hello name="Inventory"/>
<say-hello name="Billing"/>
~~~

Phần triển khai echo chỉ viết một lần; mỗi lần gọi cung cấp giá trị riêng cho attribute name.

Macro phù hợp khi nhiều nơi cần chạy cùng một chuỗi task với một vài đầu vào thay đổi. Ví dụ:

- Copy resource của nhiều module theo cùng quy tắc.
- Tạo thư mục cha cho các tệp đầu ra.
- Chuẩn bị classpath và chạy một nhóm kiểm tra.
- Tạo archive với cùng cấu trúc nhưng tên, thư mục hoặc phiên bản khác nhau.
- Ghi log và tạo marker theo cùng một quy trình.

Nếu cần một bước build có thể được gọi độc lập bằng tên target, có dependency graph riêng hoặc được chọn làm target mặc định, hãy dùng **target**. Macro tập trung vào tái sử dụng một chuỗi task như một đơn vị thao tác.

## 2. Phân biệt attribute của macro với property của Ant

Trong macro có hai cú pháp dễ nhầm:

- **@{name}** là tham số attribute của macro. Giá trị được thay thế khi macro được gọi.
- **${name}** là property của Ant. Giá trị được tra cứu theo quy tắc và phạm vi property tại thời điểm task chạy.

Ví dụ:

~~~xml
<property name="build.dir" location="build"/>

<macrodef name="show-output">
    <attribute name="module"/>
    <sequential>
        <echo message="Module: @{module}"/>
        <echo message="Build directory: ${build.dir}"/>
    </sequential>
</macrodef>

<show-output module="catalog"/>
~~~

Ở đây:

- **@{module}** lấy giá trị từ lời gọi macro, trong ví dụ là catalog.
- **${build.dir}** lấy property toàn project đã khai báo trước đó.

Cách ghi nhớ: dấu **@** đại diện cho đầu vào của lần gọi macro; dấu **$** đại diện cho property trong project hoặc phạm vi cục bộ.

Tên attribute và element của macro không phân biệt chữ hoa thường. Dù vậy, nên thống nhất cách viết chữ thường để build file dễ đọc.

## 3. Khai báo attribute bắt buộc và giá trị mặc định

Mỗi phần tử **attribute** của macrodef có tên. Nếu không khai báo default, người gọi phải truyền attribute đó. Nếu khai báo default, người gọi có thể bỏ qua và macro sử dụng giá trị mặc định.

~~~xml
<macrodef name="make-dir">
    <attribute name="dir"/>
    <attribute name="mode" default="normal"/>
    <sequential>
        <echo message="Create @{dir} with mode @{mode}"/>
        <mkdir dir="@{dir}"/>
    </sequential>
</macrodef>
~~~

Hai cách gọi:

~~~xml
<make-dir dir="build/classes"/>
<make-dir dir="build/generated" mode="generated"/>
~~~

Trong lần gọi đầu, **mode** nhận giá trị normal. Trong lần gọi thứ hai, người gọi truyền giá trị generated để thay thế mặc định.

Một attribute không có default là bắt buộc. Nếu thiếu attribute bắt buộc, Ant báo lỗi khi cấu hình hoặc thực thi macro instance.

### Đặt mô tả cho từng attribute

Có thể thêm **description** để giải thích ý nghĩa của đầu vào:

~~~xml
<macrodef name="package-module">
    <attribute name="module"
               description="Tên module được đóng gói"/>
    <attribute name="version"
               default="1.0.0"
               description="Phiên bản artifact"/>
    <sequential>
        <echo message="Package @{module}, version @{version}"/>
    </sequential>
</macrodef>
~~~

Mô tả không thay đổi cách chạy macro; nó là tài liệu cho người đọc build file và công cụ trợ giúp.

### Dùng attribute trước đó làm default

Giá trị mặc định của attribute có thể tham chiếu một attribute được khai báo trước đó:

~~~xml
<macrodef name="module-path">
    <attribute name="module"/>
    <attribute name="src"
               default="modules/@{module}/src"/>
    <sequential>
        <echo message="Source directory: @{src}"/>
    </sequential>
</macrodef>
~~~

Khi gọi:

~~~xml
<module-path module="catalog"/>
~~~

macro dùng đường dẫn mặc định **modules/catalog/src**. Người gọi vẫn có thể truyền **src** nếu module có cấu trúc đặc biệt.

Nên khai báo attribute được tham chiếu trước attribute dùng nó làm default để ý nghĩa của giao diện dễ theo dõi.

## 4. Nhận task con bằng element

Attribute phù hợp với giá trị đơn như tên, đường dẫn, phiên bản hoặc cờ bật/tắt. Khi người gọi cần truyền một nhóm task hoặc resource collection có cấu trúc, hãy khai báo **element**.

Ví dụ:

~~~xml
<macrodef name="run-checks">
    <attribute name="module"/>
    <element name="checks"/>
    <sequential>
        <echo message="Checking module @{module}"/>
        <checks/>
        <echo message="Checks completed for @{module}"/>
    </sequential>
</macrodef>
~~~

Lời gọi macro cung cấp phần tử checks:

~~~xml
<run-checks module="catalog">
    <checks>
        <echo message="Run catalog validation"/>
        <condition property="catalog.buildfile.available">
            <available file="modules/catalog/build.xml"/>
        </condition>
    </checks>
</run-checks>
~~~

Nội dung bên trong **checks** được đặt vào vị trí **<checks/>** trong mẫu macro. Nhờ vậy, macro kiểm soát trình tự chung nhưng người gọi vẫn có thể đưa task cụ thể vào.

Element là bắt buộc theo mặc định. Nếu macro cần nhận một khối task tùy chọn, khai báo **optional="true"**:

~~~xml
<macrodef name="prepare-module">
    <attribute name="module"/>
    <element name="before" optional="true"/>
    <sequential>
        <echo message="Preparing @{module}"/>
        <before/>
        <mkdir dir="build/@{module}"/>
    </sequential>
</macrodef>
~~~

Có thể gọi với hoặc không có before:

~~~xml
<prepare-module module="catalog">
    <before>
        <echo message="Run custom preparation"/>
    </before>
</prepare-module>

<prepare-module module="billing"/>
~~~

Với lời gọi thứ hai, phần tử before không được cung cấp và vị trí tương ứng trong mẫu không thực hiện task tùy chọn nào.

Nếu không khai báo optional, người gọi phải cung cấp element đã định nghĩa. Đây là cách macrodef thể hiện rõ phần nào là bắt buộc trong hợp đồng đầu vào.

## 5. Element implicit để nhận task con trực tiếp

Nếu macro chỉ có một vùng nhận task con, có thể khai báo element với **implicit="true"**. Khi đó, người gọi không cần bọc các task bằng một thẻ element có tên riêng.

~~~xml
<macrodef name="with-build-log">
    <attribute name="label"/>
    <element name="tasks" implicit="true"/>
    <sequential>
        <echo message="Start @{label}"/>
        <tasks/>
        <echo message="Finish @{label}"/>
    </sequential>
</macrodef>
~~~

Lời gọi:

~~~xml
<with-build-log label="compile">
    <mkdir dir="build/classes"/>
    <echo message="Compile Java sources"/>
</with-build-log>
~~~

Các task lồng trực tiếp trong **with-build-log** được đưa vào vị trí **<tasks/>** của macro.

Một macro chỉ được có một element implicit. Vì vậy, chỉ dùng cách này khi có một vùng nội dung task con rõ ràng. Nếu macro có nhiều vùng nội dung như before, checks và after, hãy khai báo element tường minh để người gọi đặt đúng task vào đúng vị trí.

## 6. Nhận văn bản trực tiếp bằng text

Macrodef có thể nhận nội dung văn bản trực tiếp thông qua phần tử **text**. Nếu macro không khai báo text, phần văn bản lồng trực tiếp trong lời gọi macro là không hợp lệ.

~~~xml
<macrodef name="log-message">
    <text name="message" trim="true"
          description="Thông điệp cần ghi log"/>
    <sequential>
        <echo message="BUILD: @{message}"/>
    </sequential>
</macrodef>
~~~

Lời gọi:

~~~xml
<log-message>Preparing release</log-message>
~~~

Ant đưa phần văn bản lồng vào attribute **message** của macro. **trim="true"** loại bỏ khoảng trắng ở đầu và cuối nội dung. Nếu cần giữ nguyên khoảng trắng, bỏ trim hoặc đặt false.

Có thể cho phép văn bản không bắt buộc:

~~~xml
<text name="message" optional="true" trim="true"/>
~~~

Không dùng text cho một cấu trúc task phức tạp. Nếu người gọi cần truyền nhiều task hoặc resource collection, element thường rõ ràng và dễ bảo trì hơn.

## 7. Kiểm soát việc mở rộng property trong attribute

Khi macro nhận một attribute, Ant xử lý property reference trong giá trị attribute. Theo mặc định, macrodef có thể mở rộng property hai lần để hỗ trợ các trường hợp giá trị macro chứa tham chiếu property được tạo ra sau bước thay thế attribute.

Từ Ant 1.8.3, có thể đặt **doubleexpanding="false"** để chỉ mở rộng một lần:

~~~xml
<macrodef name="show-literal">
    <attribute name="message" doubleexpanding="false"/>
    <sequential>
        <echo message="@{message}"/>
    </sequential>
</macrodef>
~~~

Ví dụ truyền một property reference như văn bản cần giữ nguyên:

~~~xml
<show-literal message="$${basedir}"/>
~~~

Với doubleexpanding tắt, macro có thể giữ **${basedir}** như chuỗi literal thay vì tiếp tục mở rộng nó ở lần xử lý thứ hai. Cần chọn cách escape phù hợp với nơi giá trị đi qua; nếu muốn macro nhận giá trị property đã phân giải, hãy dùng cách viết property thông thường.

### Escape ký hiệu @ trong thân macro

Trong mẫu macro, **@{name}** là cú pháp thay thế attribute. Nếu cần ghi ra ký tự literal **@{name}** mà không muốn macro thay thế, dùng **@@{name}**:

~~~xml
<macrodef name="show-syntax">
    <sequential>
        <echo message="Macro syntax is @@{attribute-name}"/>
    </sequential>
</macrodef>
~~~

Cách escape này hữu ích khi macro tạo tài liệu hoặc sinh một tệp khác có chứa cú pháp macro.

## 8. Vì sao property toàn cục gây lỗi khi macro được gọi nhiều lần?

Property Ant thông thường có tính chất chỉ thiết lập một lần. Sau khi một property đã có giá trị, task property tiếp theo cùng tên không thay thế giá trị đó.

Xét macro sau:

~~~xml
<macrodef name="make-parent">
    <attribute name="file"/>
    <sequential>
        <dirname property="parent" file="@{file}"/>
        <mkdir dir="${parent}"/>
    </sequential>
</macrodef>
~~~

Gọi hai lần:

~~~xml
<make-parent file="build/catalog/catalog.jar"/>
<make-parent file="build/billing/billing.jar"/>
~~~

Ở lần gọi đầu, property **parent** được thiết lập thành **build/catalog**. Lần gọi thứ hai cố thiết lập cùng property thành **build/billing**, nhưng property đã tồn tại nên giá trị đầu tiên vẫn được giữ. Macro có thể tiếp tục tạo sai thư mục **build/catalog**.

Đây là lỗi thường gặp khi macro dùng các property tạm có tên cố định. Nó có thể không xuất hiện khi chỉ gọi macro một lần, nhưng sẽ lộ ra khi tái sử dụng cho nhiều module hoặc nhiều đường dẫn.

Một cách cũ là tạo tên property duy nhất bằng cách nối tên property với attribute đầu vào:

~~~xml
<dirname property="parent.@{file}" file="@{file}"/>
<mkdir dir="${parent.@{file}}"/>
~~~

Cách này tránh đụng tên nhưng làm không gian property toàn project bị tích lũy nhiều tên khó quản lý. Cơ chế **local** giải quyết vấn đề này trực tiếp hơn.

## 9. Khai báo property cục bộ bằng local

Task **local** khai báo một property trong phạm vi hiện tại. Property cục bộ có thể che khuất (shadow) property cùng tên ở phạm vi cao hơn, nhưng không làm thay đổi giá trị của property ở phạm vi cao hơn đó.

Cú pháp:

~~~xml
<local name="parent"/>
~~~

Phải khai báo local **trước** task thiết lập property:

~~~xml
<macrodef name="make-parent">
    <attribute name="file"/>
    <sequential>
        <local name="parent"/>
        <dirname property="parent" file="@{file}"/>
        <mkdir dir="${parent}"/>
    </sequential>
</macrodef>
~~~

Bây giờ mỗi lần gọi macro có phạm vi local riêng cho property **parent**:

~~~xml
<make-parent file="build/catalog/catalog.jar"/>
<make-parent file="build/billing/billing.jar"/>
~~~

Lần đầu property local **parent** là **build/catalog**. Khi macro invocation kết thúc, phạm vi local kết thúc. Lần gọi tiếp theo tạo một property local **parent** mới với giá trị **build/billing**.

Không có property **parent** toàn cục bị tạo hoặc bị thay đổi. Mỗi lần gọi có thể dùng cùng tên tạm mà không va chạm.

### Local không làm property trở thành mutable

Local chỉ thay đổi **phạm vi tồn tại**, không thay đổi nguyên tắc một property chỉ được thiết lập một lần trong phạm vi của nó.

Ví dụ, trong cùng một macro invocation, nếu property local **parent** đã được thiết lập thì một task property sau đó không thể ghi đè nó theo cơ chế thông thường. Nếu cần một giá trị khác, hãy dùng tên property local khác hoặc thiết kế lại trình tự tính toán.

## 10. Các phạm vi local trong Ant

Ant hỗ trợ local property ở các phạm vi block như:

- **target**: property tồn tại trong target nơi nó được khai báo.
- **sequential**: property tồn tại trong khối sequential.
- **macrodef body**: phần sequential của macro tạo phạm vi phù hợp để mỗi lần gọi có các property tạm riêng.
- **parallel/sequential task containers**: các block này cũng có thể tạo phạm vi property cục bộ theo cấu trúc thực thi.

Một local property có thể che khuất property cùng tên ở phạm vi cao hơn. Khi thoát khỏi block, property local không còn được nhìn thấy từ các target hoặc block khác.

Ví dụ local trong target:

~~~xml
<target name="prepare-report">
    <local name="report.dir"/>
    <property name="report.dir" location="build/reports"/>
    <mkdir dir="${report.dir}"/>
    <echo message="Report directory: ${report.dir}"/>
</target>
~~~

Property **report.dir** chỉ được dùng trong target này. Một target khác có thể khai báo local property cùng tên với giá trị khác mà không ảnh hưởng target trên.

Lưu ý: nếu khai báo local ở cấp project, property đó thuộc phạm vi target ẩn (anonymous target) dùng để xử lý các thao tác top-level; nó không trở thành property dùng chung cho mọi target. Vì vậy, hãy khai báo local tại đúng target hoặc block cần sử dụng.

## 11. Kết hợp macro attribute và local property trong một macro thực tế

Ví dụ sau định nghĩa macro copy resource của một module. Người gọi cung cấp thư mục nguồn, thư mục đích và pattern. Macro đếm số resource được chọn bằng property cục bộ rồi ghi log.

~~~xml
<macrodef name="copy-module-resources">
    <attribute name="from"
               description="Thư mục resource nguồn"/>
    <attribute name="to"
               description="Thư mục đầu ra"/>
    <attribute name="pattern"
               default="**/*"
               description="Pattern chọn resource"/>
    <attribute name="overwrite"
               default="false"
               description="Có ghi đè tệp đích hay không"/>

    <sequential>
        <!-- Property chỉ tồn tại trong lần gọi macro này -->
        <local name="resource.count"/>

        <mkdir dir="@{to}"/>

        <copy todir="@{to}" overwrite="@{overwrite}">
            <fileset dir="@{from}">
                <include name="@{pattern}"/>
            </fileset>
        </copy>

        <resourcecount property="resource.count">
            <fileset dir="@{from}">
                <include name="@{pattern}"/>
            </fileset>
        </resourcecount>

        <echo message="Selected @{pattern} from @{from}: ${resource.count} resource(s)"/>
    </sequential>
</macrodef>
~~~

Gọi macro cho hai module:

~~~xml
<copy-module-resources
    from="modules/catalog/src/main/resources"
    to="build/catalog/resources"
    pattern="**/*"/>

<copy-module-resources
    from="modules/billing/src/main/resources"
    to="build/billing/resources"
    pattern="**/*.properties"
    overwrite="true"/>
~~~

Mỗi invocation có cùng giao diện nhưng dữ liệu khác nhau:

- **from** và **to** là đầu vào bắt buộc.
- **pattern** mặc định chọn mọi resource nếu không truyền.
- **overwrite** mặc định false.
- **resource.count** được khai báo local, vì vậy kết quả đếm của module catalog không làm ảnh hưởng lần gọi billing.

Macro giúp tập trung quy tắc copy ở một nơi. Nếu sau này cần thêm filter hoặc đổi cách ghi log, chỉ cần sửa macro thay vì sửa từng module.

## 12. Kết hợp nested element để cho người gọi tùy chỉnh một bước

Macro có thể giữ quy trình chung nhưng cho phép người gọi chèn task đặc thù bằng element:

~~~xml
<macrodef name="build-module">
    <attribute name="name"/>
    <attribute name="src"/>
    <attribute name="dest"/>
    <element name="before-compile" optional="true"
             description="Các task cần chạy trước biên dịch"/>

    <sequential>
        <local name="module.classes"/>
        <property name="module.classes" location="@{dest}"/>

        <echo message="Building module @{name}"/>
        <before-compile/>

        <mkdir dir="${module.classes}"/>
        <javac srcdir="@{src}"
               destdir="${module.classes}"
               includeantruntime="false"/>
    </sequential>
</macrodef>
~~~

Một module có thể thêm bước riêng:

~~~xml
<build-module name="catalog"
              src="modules/catalog/src"
              dest="build/catalog/classes">
    <before-compile>
        <echo message="Generate catalog sources"/>
        <!-- Task sinh source riêng của catalog -->
    </before-compile>
</build-module>
~~~

Module khác không cần bước đặc thù:

~~~xml
<build-module name="billing"
              src="modules/billing/src"
              dest="build/billing/classes"/>
~~~

Macro kiểm soát thứ tự chuẩn; element optional cho phép mở rộng tại đúng vị trí. Local property **module.classes** tránh việc một lần gọi để lại đường dẫn của module trước cho lần gọi sau.

## 13. Thiết kế giao diện macro dễ dùng

Một macro tốt nên thể hiện rõ đầu vào và hợp đồng sử dụng.

### Đặt tên attribute theo vai trò

Ưu tiên tên diễn đạt mục đích như:

- **src** hoặc **from** cho đầu vào.
- **dest** hoặc **to** cho đầu ra.
- **module** cho tên module.
- **version** cho phiên bản.
- **pattern** cho mẫu chọn resource.
- **overwrite** cho chính sách ghi đè.

Tránh tên quá chung như **x**, **value1** hoặc **param** nếu macro có nhiều đầu vào.

### Chỉ đặt default khi giá trị thật sự phổ biến

Default giúp lời gọi ngắn hơn, nhưng default sai có thể âm thầm làm build tạo đầu ra không mong muốn. Các giá trị mặc định nên an toàn và có ý nghĩa trong hầu hết lời gọi.

Ví dụ, **overwrite="false"** có thể là mặc định thận trọng; **pattern="**/*"** chỉ phù hợp nếu macro thực sự có ý định copy mọi resource.

### Dùng attribute cho giá trị, element cho cấu trúc

Nếu đầu vào là một đường dẫn, tên hoặc cờ, dùng attribute. Nếu đầu vào là một tập task hoặc resource collection lồng nhau, dùng element. Không nên biến một chuỗi XML lớn thành attribute văn bản khó đọc.

### Không đưa mọi chi tiết thành tham số

Một macro có quá nhiều attribute và element tùy chọn có thể trở thành một API khó hiểu. Nếu hai nhóm lời gọi có quy trình khác nhau đáng kể, hãy cân nhắc tách thành hai macro nhỏ với giao diện rõ hơn.

### Giữ logic tạm trong local scope

Các property chỉ dùng để tính đường dẫn, lưu kết quả đếm hoặc tạo tên tạm nên khai báo bằng local. Property cấu hình dùng chung như build.dir, version hoặc compiler options có thể vẫn là property cấp project nếu các target cần truy cập.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gọi macro thiếu tham số bị lỗi | Attribute không có default là bắt buộc | Truyền attribute hoặc đặt default hợp lý |
| Macro không nhận task lồng | Chưa khai báo element tương ứng hoặc tên element sai | Khai báo element và dùng đúng thẻ khi gọi |
| Macro báo lỗi vì thiếu element | Element mặc định là bắt buộc | Đặt optional="true" nếu element thực sự không bắt buộc |
| Task lồng trực tiếp bị từ chối | Macro chưa khai báo implicit element hoặc text | Khai báo một element implicit hoặc phần tử text thích hợp |
| Lần gọi thứ hai dùng đường dẫn của lần đầu | Property tạm là global và đã được thiết lập | Khai báo local trước task tạo property |
| Property local vẫn thấy giá trị cũ | Local được khai báo sau khi property đã được thiết lập trong cùng scope, hoặc giá trị đã được tạo ở scope khác | Đặt local trước task định nghĩa property và kiểm tra shadowing |
| Property local không dùng được ở target khác | Property đã hết phạm vi khi target/block kết thúc | Truyền giá trị qua đầu vào phù hợp hoặc dùng property cấp project nếu thật sự cần chia sẻ |
| Giá trị macro chứa ${...} bị mở rộng ngoài ý muốn | Attribute đang dùng doubleexpanding mặc định | Cân nhắc doubleexpanding="false" và escape đúng chỗ |
| Ký hiệu @{...} trong văn bản bị thay thế | Macro hiểu đó là attribute substitution | Dùng @@{...} để ghi literal |
| Macro quá khó hiểu | Quá nhiều tham số hoặc nhiều trách nhiệm trong một macro | Chia macro theo công việc và giữ giao diện nhỏ |

## 15. Ví dụ hoàn chỉnh: macro đóng gói nhiều module

Ví dụ sau định nghĩa một macro đóng gói class của module. Mỗi lần gọi có tên module, thư mục class và thư mục đích riêng. Property tạm **module.jar** và **module.name** được giữ trong scope của macro.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="multi-module" default="package-all" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>
    <property name="version" value="1.0.0"/>

    <macrodef name="package-module">
        <attribute name="name"
                   description="Tên module"/>
        <attribute name="classes"
                   description="Thư mục class đầu vào"/>
        <attribute name="dest"
                   default="${dist.dir}"
                   description="Thư mục JAR đầu ra"/>

        <element name="extra-resources" optional="true"
                 description="Resource bổ sung cho JAR"/>

        <sequential>
            <local name="module.jar"/>
            <local name="module.name"/>

            <property name="module.name" value="@{name}"/>
            <property name="module.jar"
                      location="@{dest}/@{name}-${version}.jar"/>

            <mkdir dir="@{dest}"/>

            <jar destfile="${module.jar}"
                 duplicate="fail"
                 whenmanifestonly="fail">

                <fileset dir="@{classes}">
                    <include name="**/*.class"/>
                    <exclude name="**/*Test.class"/>
                </fileset>

                <extra-resources/>

                <manifest>
                    <attribute name="Implementation-Title"
                               value="${module.name}"/>
                    <attribute name="Implementation-Version"
                               value="${version}"/>
                </manifest>
            </jar>

            <echo message="Created ${module.jar}"/>
        </sequential>
    </macrodef>

    <target name="package-all"
            description="Đóng gói các module">

        <package-module name="catalog"
                        classes="${build.dir}/catalog/classes">
            <extra-resources>
                <fileset dir="modules/catalog/src/main/resources">
                    <include name="**/*"/>
                </fileset>
            </extra-resources>
        </package-module>

        <package-module name="billing"
                        classes="${build.dir}/billing/classes">
            <extra-resources>
                <fileset dir="modules/billing/src/main/resources">
                    <include name="**/*"/>
                </fileset>
            </extra-resources>
        </package-module>

    </target>

</project>
~~~

Trong ví dụ:

1. **package-module** định nghĩa giao diện gồm name, classes, dest và extra-resources.
2. **dest** có default là dist.dir, nên người gọi không phải truyền nếu dùng thư mục phát hành chung.
3. **extra-resources** là element tùy chọn, cho phép từng module bổ sung resource riêng.
4. **module.jar** và **module.name** là local property, nên mỗi invocation có giá trị độc lập.
5. **version** là property cấp project vì tất cả module dùng chung.
6. **duplicate="fail"** làm build phát hiện xung đột entry.
7. **whenmanifestonly="fail"** ngăn tạo JAR không có nội dung ứng dụng.

Khi chạy **ant package-all**, macro được gọi hai lần. Lần catalog và billing có thể dùng cùng tên property local mà không làm lẫn đường dẫn JAR.

## 16. Phiên bản Ant cần lưu ý

Một số khả năng của macro và local được bổ sung theo phiên bản Ant:

| Tính năng | Phiên bản Ant |
|---|---|
| macrodef | 1.6 |
| Mô tả attribute/element và text trong macrodef | 1.6.1 |
| Element implicit | 1.6.2 |
| Điều khiển backtrace của macrodef | 1.7 |
| Task local | 1.8.0 |
| Attribute doubleexpanding | 1.8.3 |

Nếu build cần chạy trên một phiên bản Ant cũ hơn, hãy kiểm tra khả năng hỗ trợ trước khi dùng các thuộc tính này. Đặc biệt, **local** không có trong Ant trước 1.8.0; những build cũ phải dùng cách đặt tên property riêng hoặc nâng cấp Ant để có scope local.

## 17. Nguyên tắc sử dụng

- Dùng macrodef để đóng gói chuỗi task có cùng quy trình nhưng khác đầu vào.
- Khai báo attribute bắt buộc cho dữ liệu mà macro không thể tự suy ra; dùng default cho giá trị phổ biến và an toàn.
- Dùng element khi người gọi cần chèn task hoặc resource collection; chỉ dùng implicit khi macro có một vùng task con duy nhất.
- Dùng text khi macro thực sự cần nhận văn bản trực tiếp.
- Phân biệt **@{attribute}** với **${property}** để tránh nhầm đầu vào macro và property của Ant.
- Khai báo **local** trước task thiết lập property tạm.
- Dùng local cho đường dẫn trung gian, kết quả đếm và tên tạm trong mỗi invocation.
- Giữ property cấp project cho cấu hình thật sự cần chia sẻ giữa nhiều target.
- Dùng doubleexpanding="false" khi attribute phải giữ nguyên property reference chưa mở rộng.
- Dùng @@ để escape cú pháp attribute literal trong thân macro.
- Chọn macro có giao diện nhỏ, tên rõ và một trách nhiệm chính.

Macrodef tạo ra một giao diện tái sử dụng cho chuỗi task; attribute và element xác định dữ liệu người gọi có thể truyền vào. Local property giữ dữ liệu tạm trong đúng target hoặc lần gọi macro, tránh lỗi do property toàn cục chỉ được thiết lập một lần. Khi hai cơ chế được dùng cùng nhau, build file có thể chia sẻ quy trình giữa nhiều module mà vẫn giữ đầu vào, trạng thái trung gian và kết quả của từng lần gọi độc lập.

## Tài liệu tham khảo

- [Apache Ant — MacroDef Task](https://ant.apache.org/manual/Tasks/macrodef.html)
- [Apache Ant — Local Task](https://ant.apache.org/manual/Tasks/local.html)
- [Apache Ant — Properties and PropertyHelpers](https://ant.apache.org/manual/properties.html)
- [Apache Ant — Frequently Asked Questions](https://ant.apache.org/faq.html)

