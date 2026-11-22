# Kết hợp phép kiểm tra bằng and, or, not và xor

Trong Apache Ant, task **condition** đánh giá một điều kiện rồi thiết lập property nếu biểu thức đúng. Một điều kiện đơn giản có thể kiểm tra property có tồn tại, một tệp có sẵn hay một giá trị có bằng chuỗi mong đợi hay không. Khi quyết định build phụ thuộc vào nhiều yếu tố cùng lúc, có thể kết hợp các phép kiểm tra bằng bốn condition container: **and**, **or**, **not** và **xor**.

Các container này cho phép biểu diễn logic Boolean ngay trong XML của build file. Thay vì viết nhiều target với những kiểm tra rời rạc, ta có thể mô tả rõ một quy tắc như “được phép publish khi đang ở môi trường production, có cấu hình deploy và chưa bật cờ bỏ qua”.

## 1. Nơi dùng and, or, not và xor

Các phần tử **and**, **or**, **not** và **xor** là các condition container. Chúng không tự thực hiện thao tác build; chúng nhận những condition khác làm phần tử con, kết hợp kết quả của chúng và trả về một giá trị đúng hoặc sai.

Thông thường, các container được đặt bên trong task **condition**:

~~~xml
<condition property="build.allowed">
    <and>
        <isset property="env"/>
        <equals arg1="${env}" arg2="ci"/>
    </and>
</condition>
~~~

Ant đánh giá hai điều kiện con:

- Property **env** phải tồn tại.
- Giá trị của **env** phải bằng chuỗi **ci**.

Chỉ khi cả hai điều kiện đúng, property **build.allowed** mới được thiết lập. Có thể dùng property đó để điều khiển target hoặc task tiếp theo.

Một condition đơn cũng có thể đặt trực tiếp trong **condition**, nhưng các container hữu ích khi biểu thức có nhiều thành phần hoặc cần nhóm logic lồng nhau.

## 2. Phép AND: tất cả điều kiện phải đúng

**and** trả về true khi tất cả condition con đều đúng. Chỉ cần một condition con sai thì kết quả AND là false.

Cú pháp:

~~~xml
<condition property="publish.allowed">
    <and>
        <isset property="deploy.config"/>
        <available file="config/production.properties" type="file"/>
        <equals arg1="${environment}" arg2="production"/>
    </and>
</condition>
~~~

Điều kiện **publish.allowed** chỉ được thiết lập khi:

1. Property **deploy.config** đã tồn tại.
2. Tệp **config/production.properties** tồn tại và là tệp.
3. Property **environment** có giá trị **production**.

Nếu thiếu một trong ba yếu tố, biểu thức AND không thỏa mãn.

Bảng chân trị của AND với hai đầu vào:

| A | B | A AND B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

AND phù hợp với quy tắc yêu cầu nhiều điều kiện bắt buộc cùng được đáp ứng, ví dụ:

- Có JDK và thư mục nguồn trước khi biên dịch.
- Có cấu hình và credential trước khi publish.
- Đang ở đúng môi trường và có artifact trước khi deploy.

### Ví dụ: chỉ biên dịch khi có mã nguồn và JDK

~~~xml
<property name="src.dir" location="src/main/java"/>

<condition property="compile.ready">
    <and>
        <available file="${src.dir}" type="dir"/>
        <isset property="java.home"/>
    </and>
</condition>

<target name="compile" if="compile.ready"
        description="Biên dịch khi đầu vào đã sẵn sàng">
    <mkdir dir="build/classes"/>
    <javac srcdir="${src.dir}"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Ở đây, target **compile** chỉ chạy phần thân khi thư mục nguồn tồn tại và property **java.home** đã được thiết lập. Trong một build thực tế, có thể bổ sung điều kiện kiểm tra công cụ hoặc cấu hình cụ thể hơn.

## 3. Phép OR: chỉ cần ít nhất một điều kiện đúng

**or** trả về true khi có ít nhất một condition con đúng. Kết quả chỉ false nếu tất cả điều kiện con đều false.

Ví dụ, build được phép chạy bộ kiểm thử nếu đang ở môi trường CI hoặc developer đã bật cờ chạy test:

~~~xml
<condition property="run.tests">
    <or>
        <equals arg1="${environment}" arg2="ci"/>
        <isset property="force.tests"/>
    </or>
</condition>
~~~

Khi **environment** bằng **ci**, điều kiện đã đúng dù property **force.tests** không tồn tại. Nếu không ở CI, property **force.tests** có thể bật bộ kiểm thử thủ công.

Bảng chân trị của OR:

| A | B | A OR B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

OR phù hợp với những quy tắc có nhiều con đường thay thế, chẳng hạn:

- Có thể dùng JDK được cài trong môi trường chuẩn hoặc đường dẫn JDK tùy chỉnh.
- Chạy test nếu là build CI hoặc người dùng yêu cầu rõ ràng.
- Cho phép đóng gói nếu có ít nhất một loại tài nguyên đầu vào.

### Ví dụ: chấp nhận một trong hai tệp cấu hình

~~~xml
<condition property="config.available">
    <or>
        <available file="config/local.properties" type="file"/>
        <available file="config/build.properties" type="file"/>
    </or>
</condition>

<target name="inspect-config" if="config.available">
    <echo message="A supported configuration file is available."/>
</target>
~~~

Chỉ cần một trong hai tệp tồn tại thì property **config.available** được thiết lập. Lưu ý: điều kiện OR chỉ xác nhận có ít nhất một tệp; nó không tự quyết định tệp nào sẽ được nạp. Logic lựa chọn cấu hình vẫn cần được khai báo riêng.

## 4. Phép NOT: đảo kết quả của một điều kiện

**not** đảo kết quả của condition con:

- Condition con đúng thì NOT trả về false.
- Condition con sai thì NOT trả về true.

Not nhận một condition con:

~~~xml
<condition property="skip.deploy.not.requested">
    <not>
        <isset property="skip.deploy"/>
    </not>
</condition>
~~~

Property **skip.deploy.not.requested** được thiết lập khi property **skip.deploy** chưa tồn tại.

Ví dụ thực tế hơn: chỉ thực hiện bước publish khi không có property yêu cầu bỏ qua:

~~~xml
<condition property="publish.enabled">
    <not>
        <isset property="skip.publish"/>
    </not>
</condition>

<target name="publish" if="publish.enabled"
        description="Publish artifact khi không bị yêu cầu bỏ qua">
    <echo message="Publishing artifact..."/>
</target>
~~~

Nếu người dùng chạy:

~~~bash
ant -Dskip.publish=true publish
~~~

Property **skip.publish** tồn tại, nên condition NOT trả về false và property **publish.enabled** không được thiết lập. Phần thân target **publish** vì thế được bỏ qua.

Nếu không truyền **skip.publish**, điều kiện NOT đúng và target có thể chạy.

### NOT có thể bọc một biểu thức phức tạp

Không chỉ đảo một condition đơn, NOT còn có thể bọc cả một container AND hoặc OR:

~~~xml
<condition property="not.ready">
    <not>
        <and>
            <available file="build/app.jar" type="file"/>
            <available file="config/runtime.properties" type="file"/>
        </and>
    </not>
</condition>
~~~

Property **not.ready** được thiết lập nếu không phải cả hai tệp đều tồn tại. Tương đương về logic:

~~~text
NOT (A AND B)
~~~

Theo định luật De Morgan, biểu thức này tương đương:

~~~text
(NOT A) OR (NOT B)
~~~

Cách viết đầu tiên thường dễ đọc hơn khi muốn diễn đạt rằng một nhóm điều kiện chưa đồng thời được đáp ứng.

## 5. Phép XOR: số điều kiện đúng phải là số lẻ

**xor** là phép OR loại trừ. Với hai đầu vào, XOR đúng khi chính xác một đầu vào đúng; nếu cả hai cùng đúng hoặc cùng sai thì kết quả false.

Trong condition container của Ant, XOR với nhiều condition con trả về true khi có **số lẻ** condition con đúng. Vì vậy, với hai đầu vào, nó tương đương quy tắc “chính xác một trong hai”.

Ví dụ, người dùng phải chọn một trong hai profile triển khai **blue** hoặc **green**:

~~~xml
<property name="deploy.blue" value="false"/>
<property name="deploy.green" value="false"/>

<condition property="deployment.choice.valid">
    <xor>
        <equals arg1="${deploy.blue}" arg2="true" casesensitive="false"/>
        <equals arg1="${deploy.green}" arg2="true" casesensitive="false"/>
    </xor>
</condition>
~~~

Có thể truyền lựa chọn từ dòng lệnh:

~~~bash
ant -Ddeploy.blue=true deploy
~~~

Hoặc:

~~~bash
ant -Ddeploy.green=true deploy
~~~

Kết quả với hai điều kiện:

| Blue | Green | XOR | Ý nghĩa |
|---|---|---|---|
| false | false | false | Chưa chọn profile nào |
| true | false | true | Chỉ chọn Blue |
| false | true | true | Chỉ chọn Green |
| true | true | false | Chọn cả hai, không hợp lệ với quy tắc loại trừ |

Với ba condition con, XOR đúng khi một hoặc cả ba đều đúng. Cụ thể, một condition đúng hoặc cả ba condition đúng đều cho kết quả true; hai condition đúng cho kết quả false. Đây là quy tắc parity (số lượng giá trị true là số lẻ), không phải “chính xác một” trong mọi trường hợp nhiều hơn hai đầu vào.

Nếu yêu cầu nghiệp vụ là **chính xác một trong ba lựa chọn**, cần kết hợp điều kiện đếm hoặc biểu thức AND/OR phù hợp; không nên giả định XOR ba đầu vào tự bảo đảm đúng một lựa chọn.

### Dùng XOR để phát hiện lựa chọn xung đột

Một cách sử dụng phổ biến là bảo đảm người dùng bật đúng một tùy chọn trong hai tùy chọn loại trừ nhau, chẳng hạn chạy server cục bộ hoặc dùng server từ xa:

~~~xml
<property name="use.local.server" value="false"/>
<property name="use.remote.server" value="false"/>

<condition property="server.selection.valid">
    <xor>
        <equals arg1="${use.local.server}" arg2="true" casesensitive="false"/>
        <equals arg1="${use.remote.server}" arg2="true" casesensitive="false"/>
    </xor>
</condition>

<target name="start-tests" if="server.selection.valid">
    <echo message="Exactly one test server mode is selected."/>
</target>
~~~

Nếu không chọn hoặc chọn đồng thời cả hai chế độ, target **start-tests** không chạy. Với các lựa chọn quan trọng, nên có thêm target báo lỗi rõ ràng khi cấu hình không hợp lệ.

## 6. Kết hợp nhiều container để tạo biểu thức lồng nhau

Các container có thể lồng tùy theo cấu trúc logic cần diễn đạt. Ví dụ, một artifact được phép publish nếu:

- Đang ở môi trường production và có tệp cấu hình deploy; **hoặc**
- Đang ở môi trường staging, có cấu hình staging và không bật cờ bỏ qua.

Biểu thức:

~~~text
(environment = production AND production-config-exists)
OR
(environment = staging AND staging-config-exists AND NOT skip-publish)
~~~

Có thể biểu diễn trong Ant:

~~~xml
<condition property="publish.allowed">
    <or>
        <and>
            <equals arg1="${environment}" arg2="production"/>
            <available file="config/production.properties" type="file"/>
        </and>

        <and>
            <equals arg1="${environment}" arg2="staging"/>
            <available file="config/staging.properties" type="file"/>
            <not>
                <isset property="skip.publish"/>
            </not>
        </and>
    </or>
</condition>
~~~

Cấu trúc XML phản ánh trực tiếp cách nhóm điều kiện:

- OR ngoài cùng cho phép một trong hai nhánh.
- AND thứ nhất yêu cầu cả hai điều kiện production.
- AND thứ hai yêu cầu cả ba điều kiện staging.
- NOT đảo kiểm tra sự tồn tại của **skip.publish**.

Khi biểu thức có nhiều cấp, nên thụt lề theo nhóm và dùng tên property có ý nghĩa. Điều này giúp người bảo trì đối chiếu XML với quy tắc nghiệp vụ mà không phải tự phân tích một biểu thức dài.

### Một ví dụ với ba nhóm điều kiện

Giả sử bước kiểm tra được phép chạy khi build là CI, hoặc khi developer bật chế độ kiểm tra cục bộ và thư mục test tồn tại:

~~~xml
<condition property="verification.enabled">
    <or>
        <equals arg1="${environment}" arg2="ci"/>
        <and>
            <equals arg1="${environment}" arg2="local"/>
            <isset property="run.local.verification"/>
            <available file="src/test" type="dir"/>
        </and>
    </or>
</condition>
~~~

Có thể đọc theo thứ tự:

1. Nếu **environment** bằng **ci**, điều kiện ngoài cùng đúng.
2. Nếu không, Ant kiểm tra nhánh AND.
3. Nhánh AND chỉ đúng khi môi trường là local, property bật kiểm tra tồn tại và thư mục test có sẵn.
4. Nếu cả hai nhánh đều sai, **verification.enabled** không được thiết lập.

## 7. Các condition đơn thường kết hợp với container

AND, OR, NOT và XOR không tự kiểm tra filesystem hay giá trị property. Chúng kết hợp các condition đơn. Một số condition thường dùng gồm:

| Condition | Mục đích | Ví dụ |
|---|---|---|
| **isset** | Kiểm tra property đã tồn tại | <code>&lt;isset property="release"/&gt;</code> |
| **equals** | So sánh hai giá trị | <code>&lt;equals arg1="env" arg2="ci"/&gt;</code> |
| **available** | Kiểm tra tệp, thư mục hoặc resource có sẵn | <code>&lt;available file="build/app.jar" type="file"/&gt;</code> |
| **os** | Kiểm tra hệ điều hành hoặc họ hệ điều hành | <code>&lt;os family="windows"/&gt;</code> |
| **uptodate** | Kiểm tra đầu ra có mới hơn các đầu vào theo timestamp | <code>&lt;uptodate targetfile="build/app.jar"&gt;...&lt;/uptodate&gt;</code> |
| **contains** | Kiểm tra chuỗi có chứa chuỗi con | <code>&lt;contains string="message" substring="release"/&gt;</code> |

Ví dụ kết hợp OS và sự tồn tại của công cụ:

~~~xml
<condition property="windows.tool.available">
    <and>
        <os family="windows"/>
        <available file="tools/build-helper.exe" type="file"/>
    </and>
</condition>
~~~

Property chỉ được thiết lập khi hệ điều hành thuộc họ Windows và tệp công cụ có tồn tại.

Với **equals**, có thể dùng **casesensitive="false"** nếu không muốn phân biệt hoa thường:

~~~xml
<equals arg1="${environment}"
        arg2="production"
        casesensitive="false"/>
~~~

Với **available**, thuộc tính **type** có thể giới hạn loại resource cần kiểm tra, chẳng hạn **file** hoặc **dir**. Nếu bỏ qua, condition kiểm tra khả năng tồn tại của đường dẫn theo cách hỗ trợ của task.

## 8. Đưa kết quả condition vào target bằng if và unless

Task **condition** thiết lập property khi biểu thức đúng. Target có thể dùng thuộc tính **if** hoặc **unless** để quyết định phần thân có được thực hiện hay không.

Ví dụ:

~~~xml
<condition property="tests.enabled">
    <or>
        <equals arg1="${environment}" arg2="ci"/>
        <isset property="force.tests"/>
    </or>
</condition>

<target name="test" if="tests.enabled"
        description="Chạy kiểm thử khi được yêu cầu">
    <junit>
        <!-- Cấu hình test -->
    </junit>
</target>
~~~

Target **test** chỉ chạy phần thân khi property **tests.enabled** tồn tại.

Có thể dùng **unless** để diễn đạt trường hợp ngược lại:

~~~xml
<condition property="skip.publish">
    <or>
        <equals arg1="${environment}" arg2="local"/>
        <isset property="dry.run"/>
    </or>
</condition>

<target name="publish" unless="skip.publish"
        description="Publish khi không ở chế độ bỏ qua">
    <echo message="Publishing..."/>
</target>
~~~

Target **publish** được thực hiện khi property **skip.publish** chưa tồn tại.

Điểm quan trọng: **if** và **unless** kiểm tra sự tồn tại của property, không đánh giá giá trị văn bản của nó như boolean. Nếu property được đặt thành chuỗi **false**, nó vẫn tồn tại và target có **if="ten-property"** vẫn được phép chạy. Vì vậy, hãy để condition tạo property chỉ khi biểu thức đúng, thay vì khai báo sẵn property kết quả với giá trị **false**.

### Condition false không tự tạo property

Ví dụ:

~~~xml
<condition property="release.ready">
    <and>
        <isset property="release.version"/>
        <available file="build/app.jar" type="file"/>
    </and>
</condition>
~~~

Nếu biểu thức sai, property **release.ready** không được thiết lập. Đây là cách phù hợp để kết hợp với **if="release.ready"**.

Không nên viết trước:

~~~xml
<property name="release.ready" value="false"/>
~~~

rồi mong task condition ghi đè thành true, vì property thông thường của Ant chỉ được thiết lập một lần. Giá trị **false** ban đầu sẽ giữ nguyên.

## 9. Ví dụ build.xml: kiểm tra trước khi đóng gói và publish

Ví dụ sau dùng AND, OR, NOT và XOR để tổ chức điều kiện cho một quy trình release. Build chỉ đóng gói khi có mã nguồn và cấu hình; publish chỉ được phép khi đang ở môi trường phù hợp, người dùng chọn đúng một kênh phát hành và không bật cờ bỏ qua.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="package" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="environment" value="local"/>

    <property name="release.channel.blue" value="false"/>
    <property name="release.channel.green" value="false"/>

    <!-- Kiểm tra đầu vào biên dịch -->
    <condition property="compile.ready">
        <and>
            <available file="${src.dir}" type="dir"/>
            <available file="config/build.properties" type="file"/>
        </and>
    </condition>

    <!-- Có thể chạy test trong CI hoặc khi được yêu cầu -->
    <condition property="tests.enabled">
        <or>
            <equals arg1="${environment}" arg2="ci"/>
            <isset property="force.tests"/>
        </or>
    </condition>

    <!-- Chính xác một trong hai kênh release phải được chọn -->
    <condition property="release.channel.valid">
        <xor>
            <equals arg1="${release.channel.blue}" arg2="true"
                    casesensitive="false"/>
            <equals arg1="${release.channel.green}" arg2="true"
                    casesensitive="false"/>
        </xor>
    </condition>

    <!-- Không được yêu cầu bỏ qua publish -->
    <condition property="publish.enabled">
        <and>
            <equals arg1="${environment}" arg2="production"/>
            <isset property="release.channel.valid"/>
            <not>
                <isset property="skip.publish"/>
            </not>
        </and>
    </condition>

    <target name="init">
        <mkdir dir="${build.dir}/classes"/>
        <mkdir dir="${build.dir}/dist"/>
    </target>

    <target name="compile" depends="init" if="compile.ready"
            description="Biên dịch khi đầu vào sẵn sàng">
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               includeantruntime="false"/>
    </target>

    <target name="test" depends="compile" if="tests.enabled"
            description="Chạy kiểm thử khi được bật">
        <echo message="Run automated tests here"/>
    </target>

    <target name="package" depends="compile" if="compile.ready"
            description="Đóng gói ứng dụng thành JAR">
        <jar destfile="${build.dir}/dist/inventory.jar"
             basedir="${build.dir}/classes"/>
    </target>

    <target name="publish" depends="package" if="publish.enabled"
            description="Publish artifact khi điều kiện release hợp lệ">
        <echo message="Publish the selected release channel here"/>
    </target>

</project>
~~~

Một số cách gọi minh họa:

~~~bash
# Build local và đóng gói
ant package

# Chạy test trong CI
ant -Denvironment=ci test

# Publish kênh Blue ở production
ant -Denvironment=production -Drelease.channel.blue=true publish

# Publish kênh Green ở production
ant -Denvironment=production -Drelease.channel.green=true publish

# Yêu cầu bỏ qua publish
ant -Denvironment=production -Drelease.channel.blue=true -Dskip.publish=true publish
~~~

Trong ví dụ, hai property kênh được đặt mặc định là **false**; user property truyền bằng **-D** được Ant thiết lập trước và giữ giá trị khi build file xử lý các khai báo. XOR bảo đảm đúng một kênh có giá trị true. AND kết hợp môi trường production, lựa chọn hợp lệ và điều kiện không bỏ qua.

Đây là ví dụ minh họa cách tổ chức điều kiện. Trong một quy trình release thật, cần bổ sung các bước kiểm tra credential, xác nhận artifact và task publish tương ứng với hệ thống triển khai.

## 10. Bảng so sánh bốn phép logic

| Container | Kết quả true khi | Cách diễn đạt thường gặp |
|---|---|---|
| **and** | Tất cả condition con đều true | Tất cả yêu cầu bắt buộc phải đạt |
| **or** | Ít nhất một condition con true | Có ít nhất một phương án hợp lệ |
| **not** | Condition con duy nhất là false | Điều kiện không xảy ra hoặc cờ không tồn tại |
| **xor** | Số condition con true là số lẻ | Hai lựa chọn: đúng một lựa chọn; nhiều đầu vào: parity lẻ |

Với hai đầu vào, có thể ghi nhớ:

| A | B | AND | OR | XOR |
|---|---|---|---|---|
| false | false | false | false | false |
| false | true | false | true | true |
| true | false | false | true | true |
| true | true | true | true | false |

NOT đảo từng giá trị: **NOT false = true** và **NOT true = false**.

Một số biểu thức tương đương hữu ích:

- **NOT (A AND B)** tương đương **(NOT A) OR (NOT B)**.
- **NOT (A OR B)** tương đương **(NOT A) AND (NOT B)**.
- Với hai đầu vào, **A XOR B** tương đương **(A OR B) AND NOT (A AND B)**.

Các biểu thức tương đương này giúp kiểm tra cách nhóm container trong XML có đúng với quy tắc mong muốn hay không.

## 11. Lỗi thường gặp khi kết hợp condition

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Target có if vẫn chạy dù property mang giá trị false | if kiểm tra sự tồn tại của property | Chỉ tạo property khi condition đúng; không dùng chuỗi false làm cờ tắt |
| AND luôn false | Có ít nhất một condition con không thỏa mãn | Kiểm tra từng điều kiện con độc lập |
| OR luôn false | Tất cả condition con đều false | Xem lại giá trị property, đường dẫn và điều kiện so sánh |
| NOT cho kết quả ngược mong đợi | Nhầm lẫn giữa property tồn tại và giá trị property | Dùng isset khi muốn kiểm tra sự tồn tại; dùng equals khi muốn so sánh giá trị |
| XOR sai khi cả hai lựa chọn đều bật | XOR không có nghĩa là “ít nhất một” | Nếu cần đúng một trong hai, XOR là phù hợp; nếu cần ít nhất một, dùng OR |
| XOR với ba đầu vào chấp nhận ba lựa chọn cùng đúng | XOR nhiều đầu vào kiểm tra số lượng true là số lẻ | Nếu cần chính xác một trong nhiều lựa chọn, phải xây dựng biểu thức kiểm tra riêng |
| Condition không thấy property mới | Property được khai báo ở target khác chưa được thực hiện hoặc tên sai | Đảm bảo property được thiết lập trước lúc condition chạy |
| Condition kiểm tra nhầm đường dẫn | Đường dẫn tương đối được phân giải theo base directory hoặc thư mục làm việc không như dự kiến | Dùng basedir/location rõ ràng và kiểm tra đường dẫn |

Khi debug một biểu thức dài, có thể tách các nhánh thành property trung gian có tên dễ hiểu. Ví dụ, tính riêng **production.config.ready** và **staging.config.ready**, sau đó kết hợp hai property đó bằng OR. Cách này làm build file dài hơn một chút nhưng thường dễ theo dõi hơn khi điều kiện có nhiều cấp.

## 12. Nguyên tắc tổ chức biểu thức điều kiện

- Dùng **and** cho các yêu cầu bắt buộc phải cùng đúng.
- Dùng **or** cho những lựa chọn thay thế, chỉ cần một phương án đúng.
- Dùng **not** để đảo một điều kiện, đặc biệt khi kiểm tra cờ bỏ qua hoặc sự vắng mặt của một yếu tố.
- Dùng **xor** khi cần số điều kiện đúng là số lẻ; với hai lựa chọn, điều đó có nghĩa chính xác một lựa chọn được bật.
- Đặt tên property kết quả theo ý nghĩa nghiệp vụ như **compile.ready**, **tests.enabled** hoặc **publish.allowed**.
- Dùng các condition đơn như **isset**, **equals**, **available** và **os** để kiểm tra từng yếu tố cụ thể.
- Thụt lề XML theo nhóm logic để biểu thức lồng nhau dễ đọc.
- Nhớ rằng **if** và **unless** kiểm tra sự tồn tại của property, còn **equals** mới so sánh giá trị văn bản.
- Không khai báo trước property kết quả với giá trị mặc định nếu mong condition có thể thiết lập nó sau đó.

Khi kết hợp đúng AND, OR, NOT và XOR, build file Ant có thể mô tả các quy tắc lựa chọn phức tạp bằng cấu trúc XML rõ ràng. Các condition đơn kiểm tra từng yếu tố, container kết hợp chúng thành biểu thức Boolean, còn task condition chuyển kết quả thành property để target sử dụng. Nhờ đó, quy trình build có thể tự quyết định bước nào phù hợp với cấu hình và môi trường hiện tại.

