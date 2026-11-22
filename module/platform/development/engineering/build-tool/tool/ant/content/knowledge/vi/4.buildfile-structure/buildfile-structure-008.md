# Escape ký tự XML, CDATA và biểu thức property trong văn bản

## Mục tiêu

Khi viết buildfile Apache Ant, ta thường đặt thông điệp, đường dẫn, đoạn mã hoặc một phần cấu hình XML bên trong các phần tử của buildfile. Những nội dung này có thể chứa ký tự đặc biệt của XML như dấu nhỏ hơn, dấu lớn hơn và dấu ampersand. Chúng cũng có thể chứa biểu thức property của Ant như ${build.dir}.

Để buildfile luôn hợp lệ và tạo ra đúng nội dung mong muốn, cần phân biệt ba cơ chế:

- **Escape XML** giúp bộ phân tích XML hiểu ký tự đặc biệt là dữ liệu thay vì cú pháp đánh dấu.
- **CDATA** cho phép viết một vùng văn bản có chứa nhiều ký tự XML đặc biệt mà không phải chuyển từng ký tự thành entity.
- **Property expansion** thay thế biểu thức ${...} bằng giá trị property do Ant quản lý.

Ba cơ chế này hoạt động ở các lớp khác nhau. Hiểu đúng thứ tự xử lý sẽ giúp tránh những lỗi khó nhận ra, nhất là khi một đoạn văn bản vừa chứa XML, vừa chứa biểu thức property.

## 1. Buildfile Ant là tài liệu XML

Một buildfile Ant thường có phần tử gốc project, bên trong là property, target và các task:

~~~xml
<project name="sample" default="show">
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo message="Build directory: ${build.dir}"/>
    </target>
</project>
~~~

Trước khi Ant thực thi task, nội dung buildfile phải được phân tích như một tài liệu XML hợp lệ. Vì vậy, các quy tắc XML vẫn áp dụng cho tên phần tử, thuộc tính và nội dung văn bản.

Có thể hình dung quá trình xử lý theo ba lớp:

| Lớp | Việc xử lý | Ví dụ |
|---|---|---|
| Bộ phân tích XML | Nhận diện phần tử, thuộc tính, text, entity và CDATA | `&amp;` được đọc thành ký tự `&` |
| Ant | Xử lý cấu hình task và thay thế property ở những vị trí task hỗ trợ | `${build.dir}` được thay bằng `build` |
| Task | Thực hiện công việc với giá trị đã nhận | `echo` in thông điệp ra log |

Điểm quan trọng là XML phải hợp lệ trước khi Ant có thể thực hiện công việc của task. Escape XML không thay thế cho property expansion; property expansion cũng không thể sửa một buildfile đã sai cú pháp XML.

## 2. Escape các ký tự đặc biệt của XML

Trong XML, một số ký tự có ý nghĩa cú pháp. Khi muốn dùng chúng như dữ liệu, hãy viết entity tương ứng.

| Ký tự cần hiển thị | Entity XML | Lý do |
|---|---|---|
| `&` | `&amp;` | Dấu bắt đầu entity hoặc character reference |
| `<` | `&lt;` | Dấu bắt đầu thẻ XML |
| `>` | `&gt;` | Có thể viết trực tiếp trong nhiều trường hợp, nhưng escape giúp nội dung nhất quán và tránh chuỗi kết thúc CDATA |
| `"` | `&quot;` | Cần escape khi dấu ngoặc kép được dùng để bao quanh giá trị thuộc tính |
| `'` | `&apos;` | Cần escape khi dấu nháy đơn được dùng để bao quanh giá trị thuộc tính |

XML có năm entity dựng sẵn là `amp`, `lt`, `gt`, `quot` và `apos`. Tên entity phân biệt chữ hoa chữ thường. Hãy viết đúng chính tả và luôn có dấu chấm phẩy ở cuối entity.

### 2.1. Trong giá trị thuộc tính

Giá trị thuộc tính XML thường được bao bằng dấu ngoặc kép hoặc dấu nháy đơn. Nếu giá trị chứa chính ký tự dùng để bao quanh nó, ký tự đó phải được escape.

~~~xml
<echo message="Research &amp; Development"/>
<echo message="Điều kiện: count &lt; 10"/>
<echo message="Thông báo: &quot;Build thành công&quot;"/>
<echo message='It&apos;s ready'/>
~~~

Nếu thuộc tính được bao bằng dấu ngoặc kép, dấu nháy đơn có thể xuất hiện trực tiếp. Tương tự, nếu thuộc tính được bao bằng dấu nháy đơn, dấu ngoặc kép có thể xuất hiện trực tiếp:

~~~xml
<echo message="It's ready"/>
<echo message='The result is "OK"'/>
~~~

Không viết dấu ampersand trần trong thuộc tính. Ví dụ sau không hợp lệ vì XML parser sẽ cố hiểu phần sau dấu ampersand là tên entity:

~~~xml
<!-- Sai: dấu & chưa được escape -->
<echo message="Research & Development"/>
~~~

Cách viết đúng:

~~~xml
<echo message="Research &amp; Development"/>
~~~

### 2.2. Trong nội dung văn bản của phần tử

Trong text node, dấu nhỏ hơn vẫn phải escape vì nó có thể được hiểu là phần mở đầu của một thẻ. Dấu ampersand cũng phải escape. Dấu ngoặc kép và dấu nháy đơn thông thường không cần escape trong text node.

~~~xml
<echo>
    Bộ đếm phải thỏa mãn count &lt; 10.
    Tên nhóm: Research &amp; Development.
    Cụm từ được hiển thị: "Build is ready".
</echo>
~~~

Ant sẽ nhận phần văn bản đã được XML parser giải mã entity. Task echo vì thế có thể in ra:

~~~text
Bộ đếm phải thỏa mãn count < 10.
Tên nhóm: Research & Development.
Cụm từ được hiển thị: "Build is ready".
~~~

Không cần escape mọi dấu lớn hơn một cách máy móc, nhưng dùng `&gt;` khi muốn hiển thị ký tự này sẽ làm cho ví dụ dễ đọc và nhất quán. Đặc biệt, chuỗi `]]>` không được xuất hiện nguyên dạng trong nội dung CDATA vì đó là dấu kết thúc CDATA.

### 2.3. Escape không làm thay đổi giá trị cuối cùng

Entity chỉ là cách viết dữ liệu trong tài liệu XML. Sau khi XML parser xử lý entity, task nhận ký tự thực tế.

Ví dụ:

~~~xml
<property name="team.label" value="Research &amp; Development"/>
<echo message="Team: ${team.label}"/>
~~~

Property team.label có giá trị là Research & Development. Khi echo in property, dấu ampersand xuất hiện bình thường. Không cần viết lại thành &amp; trong giá trị được Ant thay thế, vì bước phân tích XML đã diễn ra trước đó.

## 3. Biểu thức property của Ant trong văn bản

Ant dùng cú pháp ${property.name} để tham chiếu property. Property có thể được khai báo bằng task property, được cung cấp qua dòng lệnh, hoặc được nạp từ những nguồn cấu hình khác.

~~~xml
<project name="property-demo" default="show">
    <property name="app.name" value="Build Helper"/>
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo message="Application: ${app.name}"/>
        <echo>Output directory: ${build.dir}</echo>
    </target>
</project>
~~~

Với task echo, property có thể xuất hiện trong thuộc tính message hoặc trong nội dung văn bản của phần tử echo. Ant thay thế biểu thức bằng giá trị property tương ứng trước khi task sử dụng nội dung đó.

### 3.1. Property và entity XML là hai cú pháp khác nhau

Hai đoạn sau có mục đích khác nhau:

~~~xml
<echo message="A &amp; B"/>
<echo message="Build directory: ${build.dir}"/>
~~~

- `&amp;` là entity của XML. XML parser xử lý nó khi đọc tài liệu.
- `${build.dir}` là biểu thức property của Ant. Ant xử lý nó khi cấu hình hoặc thực thi task có hỗ trợ property expansion.

Không dùng entity XML để thay thế biểu thức property. Cũng không cần escape dấu đô la chỉ vì nó xuất hiện trong buildfile. Dấu đô la chỉ có ý nghĩa đặc biệt với Ant khi nó bắt đầu một biểu thức property hợp lệ.

### 3.2. Property chưa được khai báo

Nếu Ant không tìm thấy property được tham chiếu, biểu thức thường được giữ nguyên trong chuỗi thay thế. Ví dụ, nếu release.name chưa được khai báo:

~~~xml
<echo message="Release: ${release.name}"/>
~~~

Log có thể hiển thị nguyên văn `${release.name}`. Khi gặp kết quả như vậy, hãy kiểm tra:

1. Tên property có được viết đúng chính tả không.
2. Property đã được khai báo hoặc truyền vào build chưa.
3. Target có chạy sau bước thiết lập property hay không.
4. Có file property nào cần được nạp trước khi task sử dụng giá trị không.

Property trong Ant thường có tính chất chỉ thiết lập một lần: lần gán đầu tiên có hiệu lực và các lần gán sau không ghi đè giá trị đã có. Vì vậy, nếu giá trị hiển thị không như mong đợi, hãy kiểm tra nơi property được thiết lập đầu tiên.

### 3.3. Khi cần hiển thị nguyên văn biểu thức property

Đôi khi nội dung cần in ra là một mẫu cấu hình, tài liệu hoặc đoạn mã có chứa chuỗi `${customer.name}`. Nếu Ant thay thế chuỗi đó, nội dung mẫu sẽ bị thay đổi.

Trong các vị trí có property expansion, có thể dùng cú pháp escape của Ant là `$${...}` để giữ lại biểu thức ở dạng văn bản:

~~~xml
<project name="literal-property-demo" default="show">
    <property name="customer.name" value="An"/>

    <target name="show">
        <echo message="Giá trị: ${customer.name}"/>
        <echo message="Mẫu cần hiển thị: $${customer.name}"/>
    </target>
</project>
~~~

Dòng đầu hiển thị giá trị property. Dòng thứ hai giữ lại chuỗi `${customer.name}` để người đọc nhìn thấy cú pháp tham chiếu.

Hãy dùng cách escape này tại vị trí Ant thực hiện property expansion. Nếu task có cơ chế xử lý văn bản riêng, hãy kiểm tra cách task đó nhận và xử lý nội dung.

### 3.4. Phân biệt property với thuộc tính macro

Trong macrodef, Ant còn có cú pháp thay thế thuộc tính macro là `@{attribute}`. Cú pháp này khác với property `${property}`.

~~~xml
<macrodef name="greet">
    <attribute name="who"/>
    <sequential>
        <echo>Xin chào @{who}; project là ${ant.project.name}</echo>
    </sequential>
</macrodef>

<target name="show">
    <greet who="cả nhóm"/>
</target>
~~~

Ở ví dụ này, @{who} lấy giá trị thuộc tính được truyền vào macro, còn `${ant.project.name}` tham chiếu một property của Ant. Không nên nhầm hai cú pháp khi đọc hoặc viết nội dung buildfile.

## 4. Dùng CDATA cho đoạn văn bản có nhiều ký tự XML

CDATA là một vùng nội dung văn bản trong XML. Cú pháp mở và đóng của nó là:

~~~xml
<![CDATA[
Nội dung văn bản
]]>
~~~

Bên trong vùng CDATA, các ký tự như `<`, `>` và `&` được đọc như văn bản thông thường. Điều này hữu ích khi cần đặt đoạn mã, ví dụ XML, biểu thức điều kiện hoặc nội dung có nhiều ký tự đặc biệt vào trong một phần tử của buildfile.

Ví dụ, thay vì escape từng dấu trong đoạn mã:

~~~xml
<echo>
    if (count &lt; 10 &amp;&amp; ready) {
        print("Build is ready");
    }
</echo>
~~~

Có thể viết bằng CDATA:

~~~xml
<echo><![CDATA[
if (count < 10 && ready) {
    print("Build is ready");
}
]]></echo>
~~~

XML parser chuyển phần CDATA thành nội dung văn bản của phần tử echo. Task echo nhận văn bản đó và in ra log.

### 4.1. CDATA chỉ áp dụng cho nội dung phần tử

CDATA phải nằm trong nội dung của một phần tử XML. Không thể dùng cú pháp CDATA bên trong giá trị thuộc tính.

Cách sau không hợp lệ:

~~~xml
<!-- Sai: CDATA không phải cú pháp escape cho thuộc tính -->
<echo message="<![CDATA[count < 10]]>"/>
~~~

Nếu muốn đặt điều kiện trong thuộc tính, hãy dùng entity XML:

~~~xml
<echo message="Điều kiện: count &lt; 10"/>
~~~

Nếu đoạn văn bản dài và có nhiều ký tự đặc biệt, có thể chuyển sang phần nội dung của phần tử:

~~~xml
<echo><![CDATA[
Điều kiện:
    count < 10 && ready
]]></echo>
~~~

### 4.2. Entity không được giải mã bên trong CDATA

CDATA làm cho nội dung được xem là văn bản thô đối với XML parser. Vì vậy, entity viết bên trong CDATA không được giải mã như entity XML thông thường.

~~~xml
<echo>A &amp; B</echo>
<echo><![CDATA[A &amp; B]]></echo>
~~~

Kết quả của dòng đầu là A & B. Kết quả của dòng thứ hai chứa nguyên văn A &amp; B.

Đây là điểm cần nhớ khi chuyển một đoạn văn bản từ text node thông thường sang CDATA. Nếu nội dung cần hiển thị ký tự ampersand, hãy viết trực tiếp dấu ampersand bên trong CDATA; không viết entity &amp; trừ khi thực sự muốn hiển thị cả chuỗi entity đó.

### 4.3. CDATA không thể chứa trực tiếp chuỗi kết thúc của nó

Chuỗi `]]>` đóng vùng CDATA. Vì vậy, nếu nội dung cần có chính chuỗi này, không thể đặt nguyên chuỗi đó bên trong một vùng CDATA duy nhất.

Có thể chia nội dung thành hai vùng CDATA liền nhau. XML parser ghép phần văn bản của chúng thành một chuỗi liên tục:

~~~xml
<echo><![CDATA[Phần trước: ]]]]><![CDATA[> phần sau.]]></echo>
~~~

Vùng CDATA thứ nhất kết thúc sau hai dấu ngoặc vuông, vùng thứ hai bắt đầu bằng dấu lớn hơn. Khi đọc tài liệu, XML parser ghép hai phần thành văn bản có chứa chuỗi `]]>`.

CDATA cũng không thể lồng vào một CDATA khác. Nếu nội dung có nhiều vùng cần xử lý, hãy chia chúng thành các vùng riêng biệt hoặc dùng entity XML ở những vị trí phù hợp.

### 4.4. CDATA không tắt property expansion của Ant

Đây là điểm dễ gây nhầm lẫn nhất: CDATA chỉ quy định cách XML parser đọc ký tự. Nó không phải cơ chế vô hiệu hóa xử lý property của Ant.

Ví dụ:

~~~xml
<project name="cdata-property-demo" default="show">
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo><![CDATA[
Thư mục build: ${build.dir}
Mẫu property: $${customer.name}
        ]]></echo>
    </target>
</project>
~~~

Với task echo, biểu thức `${build.dir}` vẫn được thay bằng giá trị property. Biểu thức đã escape `$${customer.name}` được giữ lại dưới dạng `${customer.name}`.

Do đó, khi dùng CDATA, hãy quyết định riêng hai điều:

- Có cần bảo vệ ký tự XML khỏi việc được hiểu là cú pháp đánh dấu không? Nếu có, dùng CDATA.
- Có cần giữ nguyên biểu thức property của Ant không? Nếu có, escape biểu thức property theo cú pháp Ant tại vị trí được Ant xử lý.

Hai quyết định này độc lập với nhau.

## 5. Kết hợp escape XML, CDATA và property trong cùng buildfile

Một buildfile có thể dùng cả ba cơ chế ở các vị trí khác nhau. Ví dụ sau khai báo property có dấu ampersand, hiển thị một điều kiện có dấu nhỏ hơn và in một đoạn XML mẫu có chứa property:

~~~xml
<project name="text-handling-demo" default="show">
    <property name="app.name" value="Research &amp; Build Tools"/>
    <property name="build.dir" value="build"/>
    <property name="limit" value="10"/>

    <target name="show">
        <!-- Entity XML được giải mã trước khi echo sử dụng giá trị -->
        <echo message="Application: ${app.name}"/>

        <!-- Dấu nhỏ hơn được escape trong text node -->
        <echo>Điều kiện kiểm tra: count &lt; ${limit}</echo>

        <!-- CDATA cho phép giữ nguyên cú pháp XML trong văn bản -->
        <echo><![CDATA[
Đoạn XML minh họa:
<target name="compile">
    <mkdir dir="${build.dir}/classes"/>
</target>

Property cần thay thế: ${app.name}
Property cần hiển thị nguyên văn: $${customer.name}
        ]]></echo>
    </target>
</project>
~~~

Trong ví dụ này:

1. `&amp;` giúp thuộc tính value hợp lệ theo XML. Property app.name sau đó có giá trị chứa ký tự ampersand thực.
2. `&lt;` cho phép viết dấu nhỏ hơn trong text node. Khi echo in ra, nội dung hiển thị dấu nhỏ hơn.
3. CDATA cho phép đưa thẻ target và mkdir vào nội dung văn bản mà không làm XML parser nhầm chúng với cấu trúc buildfile bên ngoài.
4. Property `${build.dir}` và `${app.name}` bên trong nội dung CDATA vẫn được Ant xử lý ở vị trí echo hỗ trợ property expansion.
5. `$${customer.name}` giữ lại biểu thức property để đoạn mẫu có thể được đọc hoặc dùng ở bước xử lý sau.

Khi xây dựng ví dụ tương tự, hãy kiểm tra cả cấu trúc XML bên ngoài lẫn nội dung cuối cùng mà task nhận được. Một buildfile có thể hợp lệ về XML nhưng vẫn cho ra văn bản không đúng vì property bị thay thế ngoài ý muốn.

## 6. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| XML parser báo lỗi gần dấu ampersand | Dấu ampersand chưa được escape hoặc tên entity không tồn tại | Viết `&amp;` nếu muốn hiển thị dấu ampersand |
| XML parser báo lỗi gần dấu nhỏ hơn trong thuộc tính hoặc text | Dấu nhỏ hơn được viết như ký tự dữ liệu | Dùng `&lt;` hoặc chuyển đoạn văn bản phù hợp vào CDATA |
| Giá trị thuộc tính làm vỡ cấu trúc XML | Có dấu ngoặc trùng với dấu dùng để bao thuộc tính | Đổi loại dấu bao hoặc dùng `&quot;` / `&apos;` |
| CDATA không có tác dụng trong thuộc tính | CDATA chỉ dùng được trong nội dung phần tử | Escape ký tự theo quy tắc thuộc tính XML |
| Nội dung CDATA vẫn bị thay property | CDATA không tắt property expansion của Ant | Dùng `$${...}` cho biểu thức cần giữ nguyên |
| Log hiển thị `&amp;` thay vì dấu ampersand | Entity được đặt bên trong CDATA | Viết dấu ampersand trực tiếp nếu muốn hiển thị ký tự đó |
| XML parser báo lỗi gần `]]>` | Nội dung CDATA chứa chuỗi kết thúc CDATA | Chia nội dung thành hai vùng CDATA liền nhau |
| Log còn nguyên biểu thức property | Property chưa tồn tại, sai tên hoặc không được nạp đúng lúc | Kiểm tra khai báo, thứ tự nạp và tên property |
| Log không giữ được biểu thức property như mẫu | Ant đã thay property trước khi task sử dụng nội dung | Escape thành `$${name}` tại vị trí có property expansion |

### 6.1. Phân biệt lỗi XML và lỗi property

Khi build thất bại, hãy xác định lỗi xảy ra ở lớp nào:

- **Lỗi cú pháp XML:** Ant chưa thể đọc buildfile. Kiểm tra thẻ đóng/mở, dấu ngoặc thuộc tính, entity và CDATA. Thông báo thường có vị trí dòng hoặc cột.
- **Property không có giá trị như mong muốn:** XML có thể vẫn hợp lệ, nhưng chuỗi sau thay thế không đúng. Kiểm tra tên property, nơi khai báo, thứ tự nạp và giá trị được thiết lập đầu tiên.
- **Task tạo ra nội dung khác mong đợi:** kiểm tra task có hỗ trợ xử lý property ở vị trí đang dùng hay không, sau đó kiểm tra nội dung thực tế mà task nhận được.

Có thể thêm một task echo tạm thời để in giá trị cần kiểm tra:

~~~xml
<echo message="app.name=[${app.name}]"/>
<echo message="build.dir=[${build.dir}]"/>
~~~

Dấu ngoặc vuông giúp nhận ra khoảng trắng ở đầu hoặc cuối giá trị. Khi cần thêm thông tin về quá trình build, chạy Ant với tùy chọn verbose:

~~~text
ant -verbose -f build.xml show
~~~

Tùy chọn này cung cấp thêm log để theo dõi quá trình đọc và thực thi build. Sau khi tìm được nguyên nhân, hãy bỏ các thông điệp chẩn đoán không còn cần thiết.

## 7. Thực hành tốt khi viết nội dung văn bản trong buildfile

- Escape dấu ampersand và dấu nhỏ hơn trong text node hoặc giá trị thuộc tính.
- Dùng entity XML khi nội dung ngắn và chỉ có một vài ký tự đặc biệt.
- Dùng CDATA cho đoạn mã hoặc văn bản dài có nhiều ký tự như dấu nhỏ hơn, dấu lớn hơn và ampersand.
- Không đặt CDATA trong giá trị thuộc tính.
- Không giả định CDATA ngăn Ant thay thế property.
- Dùng `$${...}` khi cần giữ nguyên cú pháp property trong vị trí Ant thực hiện property expansion.
- Kiểm tra property đã được thiết lập trước khi task sử dụng nó; chú ý đặc tính thiết lập một lần của property.
- Khi buildfile không đọc được, sửa lỗi XML trước. Khi XML đã hợp lệ nhưng kết quả sai, kiểm tra bước property expansion và hành vi của task.
- Dùng echo với giá trị được đặt trong dấu phân cách để kiểm tra khoảng trắng và nội dung thực tế.
- Giữ ví dụ XML trong CDATA tách biệt, dễ nhận ra với cấu trúc buildfile thật để người bảo trì không nhầm đoạn minh họa với task sẽ được Ant thực thi.

## 8. Tự kiểm tra

Trước khi hoàn tất một đoạn văn bản trong buildfile, hãy tự trả lời các câu hỏi sau:

1. Nội dung đang nằm trong giá trị thuộc tính, text node hay CDATA?
2. Có dấu ampersand hoặc dấu nhỏ hơn nào đang được viết như dữ liệu trong XML thông thường mà chưa escape không?
3. Dấu ngoặc dùng để bao thuộc tính có xuất hiện lại bên trong giá trị không?
4. Biểu thức property có chủ đích được thay bằng giá trị hay cần hiển thị nguyên văn?
5. Nếu dùng CDATA, nội dung có chứa chuỗi kết thúc CDATA không?
6. Task đang dùng có hỗ trợ property expansion trong vị trí văn bản đó không?
7. Nội dung cuối cùng được in ra hoặc truyền cho task có đúng như dự định không?

Khi trả lời được các câu hỏi này, việc lựa chọn giữa entity XML, CDATA và cú pháp escape property sẽ rõ ràng hơn.
