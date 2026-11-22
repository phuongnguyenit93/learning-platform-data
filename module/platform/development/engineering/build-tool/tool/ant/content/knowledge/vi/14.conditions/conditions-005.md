# Phân biệt kiểm tra sự tồn tại của property với kiểm tra giá trị boolean trong Apache Ant

Trong Apache Ant, thuộc tính if và unless thường được dùng để quyết định một target có thực hiện hay không. Điểm dễ nhầm là kiểm tra một property **đã được khai báo hay chưa** khác với kiểm tra giá trị của property đó có phải true hay false.

Ví dụ, property có tên feature.enabled được đặt giá trị false vẫn là một property đã tồn tại. Vì vậy, cú pháp if="feature.enabled" có thể cho target chạy dù giá trị của property là false. Muốn kiểm tra giá trị boolean, cần dùng property expansion theo đúng phiên bản Ant, hoặc tính toán điều kiện bằng task condition.

Nắm rõ sự khác biệt này giúp tránh các lỗi như target deploy vẫn chạy dù cấu hình đã đặt deploy.enabled=false, hoặc target kiểm thử bị bỏ qua chỉ vì một property tồn tại.

## 1. Property trong Ant là một cặp tên và giá trị

Property của Ant là một cặp key/value được dùng để truyền cấu hình vào buildfile. Ví dụ:

~~~xml
<property name="feature.enabled" value="false" />
<property name="app.version" value="2.1.0" />
<property name="build.dir" location="build" />
~~~

Ba property trên đều đã được thiết lập:

- feature.enabled có giá trị văn bản false.
- app.version có giá trị 2.1.0.
- build.dir chứa đường dẫn được Ant phân giải từ location.

Ant không tự xem mọi property có giá trị false là property chưa được đặt. Trạng thái “đã tồn tại” và nội dung “giá trị là false” là hai khái niệm riêng.

Có thể hình dung:

| Tên property | Đã được thiết lập? | Giá trị |
|---|---|---|
| feature.enabled | Có | false |
| debug.enabled | Có | true |
| deploy.approved | Có | (chuỗi rỗng) |
| test.enabled | Không | Không có giá trị |

Property có thể được thiết lập bằng task property, file Properties, tham số -D trên dòng lệnh hoặc task condition. Một khi đã được thiết lập, property thông thường có tính bất biến: các lần khai báo sau không thay thế giá trị cũ.

## 2. if="property" kiểm tra sự tồn tại, không kiểm tra true/false

Với cú pháp truyền thống của target, Ant xem nội dung thuộc tính if là tên property cần kiểm tra.

~~~xml
<project name="if-existence" default="show">
    <property name="feature.enabled" value="false" />

    <target name="show" if="feature.enabled">
        <echo message="Feature target is running" />
    </target>
</project>
~~~

Khi chạy:

~~~bash
ant show
~~~

Target show vẫn được thực hiện. Lý do là feature.enabled đã tồn tại. Ant không đọc giá trị false để kết luận điều kiện sai trong cú pháp if="feature.enabled".

Tương tự:

~~~xml
<target name="skip-when-defined" unless="feature.enabled">
    <echo message="This target runs only when feature.enabled is not set" />
</target>
~~~

Target skip-when-defined không chạy khi feature.enabled đã được thiết lập, kể cả khi giá trị là false, no hoặc chuỗi rỗng.

Có thể tóm tắt cách kiểm tra truyền thống:

| Cú pháp | Điều kiện để target chạy |
|---|---|
| if="feature.enabled" | Property feature.enabled phải tồn tại |
| unless="feature.enabled" | Property feature.enabled phải chưa tồn tại |

Vì vậy, nếu mục tiêu chỉ là kiểm tra xem người dùng có truyền một tùy chọn hay không, cách này rất hữu ích. Ví dụ, chỉ cần biết người gọi có cung cấp -Dverbose hay chưa, không cần quan tâm giá trị cụ thể.

Nhưng nếu property có thể nhận cả true và false, không nên dùng tên property trực tiếp với kỳ vọng Ant sẽ tự đánh giá nội dung boolean.

## 3. Property expansion để kiểm tra giá trị boolean từ Ant 1.8.0

Từ Apache Ant 1.8.0, có thể dùng property expansion trong if và unless để Ant đánh giá các giá trị boolean phổ biến.

Ví dụ:

~~~xml
<project name="boolean-condition" default="show">
    <target name="show" if="${feature.enabled}">
        <echo message="Feature is enabled" />
    </target>
</project>
~~~

Chạy với giá trị true:

~~~bash
ant -Dfeature.enabled=true show
~~~

Target được thực hiện.

Chạy với giá trị false:

~~~bash
ant -Dfeature.enabled=false show
~~~

Target bị bỏ qua.

Trong cú pháp này, biểu thức ${feature.enabled} được thay thế bằng giá trị property trước khi điều kiện được đánh giá. Ant nhận biết các giá trị true-like và false-like:

| Giá trị sau khi thay thế | Kết quả với if="${feature.enabled}" | Kết quả với unless="${feature.enabled}" |
|---|---|---|
| true | Cho chạy | Bỏ qua |
| on | Cho chạy | Bỏ qua |
| yes | Cho chạy | Bỏ qua |
| false | Bỏ qua | Cho chạy |
| off | Bỏ qua | Cho chạy |
| no | Bỏ qua | Cho chạy |

Các giá trị này không phân biệt chữ hoa và chữ thường theo cách đánh giá boolean của Ant. Ví dụ TRUE, On hoặc YES cũng có thể biểu diễn trạng thái đúng.

### 3.1. So sánh hai cú pháp trên cùng một property

Ví dụ dưới đây minh họa sự khác biệt rõ ràng:

~~~xml
<project name="compare-if" default="run">
    <property name="feature.enabled" value="false" />

    <target name="run" if="feature.enabled">
        <echo message="Existence check: target runs" />
    </target>

    <target name="run-boolean" if="${feature.enabled}">
        <echo message="Boolean check: target runs only when true" />
    </target>
</project>
~~~

Nếu chạy ant run, target chạy vì property feature.enabled tồn tại.

Nếu chạy ant run-boolean, Ant thay thế biểu thức bằng false và bỏ qua target.

Trong thực tế, hai target thường được đặt tên theo chức năng riêng. Ví dụ:

- if="debug.enabled" có thể dùng khi chỉ cần biết tùy chọn debug đã được khai báo.
- if="${debug.enabled}" dùng khi muốn giá trị debug.enabled phải là true-like.
- unless="skip.tests" dùng khi muốn bỏ qua test nếu property skip.tests tồn tại.
- unless="${skip.tests}" dùng khi chỉ bỏ qua test khi skip.tests mang giá trị true-like.

### 3.2. Giá trị khác true/false không tự động là boolean

Khi dùng property expansion, Ant nhận biết true, on, yes và false, off, no. Các giá trị khác được xem như tên property cần kiểm tra sự tồn tại.

Ví dụ:

~~~xml
<target name="publish" if="${release.channel}">
    <echo message="Publish target selected" />
</target>
~~~

Nếu release.channel=production, Ant không xem production là boolean true. Nó sẽ coi chuỗi production là tên property và kiểm tra property đó có tồn tại hay không.

Nếu mục tiêu là kiểm tra một giá trị văn bản cụ thể, chẳng hạn release.channel phải bằng production, hãy dùng task condition với equals thay vì dùng if như một phép so sánh chuỗi.

### 3.3. Property chưa được thiết lập

Nếu feature.enabled chưa tồn tại, biểu thức ${feature.enabled} không có giá trị để thay thế và có thể còn nguyên dưới dạng văn bản. Với điều kiện target, chuỗi chưa được thay thế này không phải một giá trị true-like nên target if bị bỏ qua; với unless, target không bị bỏ qua bởi điều kiện đó.

Tuy nhiên, để buildfile dễ đọc và ít phụ thuộc vào biểu thức chưa được định nghĩa, nên cung cấp mặc định rõ ràng hoặc dùng task condition để tạo property điều kiện.

## 4. Dùng task condition để tính toán boolean

Khi cần kiểm tra một biểu thức thay vì chỉ kiểm tra một property, dùng task condition. Task này đặt property khi điều kiện lồng bên trong đúng. Mặc định, property được đặt thành chuỗi true; nếu điều kiện sai, property không được thiết lập.

Ví dụ:

~~~xml
<project name="condition-example" default="deploy">
    <condition property="deploy.enabled">
        <equals arg1="${target.environment}"
                arg2="production"
                casesensitive="false" />
    </condition>

    <target name="deploy" if="deploy.enabled">
        <echo message="Deploying production application" />
    </target>
</project>
~~~

Nếu target.environment bằng production, task condition đặt deploy.enabled thành true. Target deploy có if="deploy.enabled" nên được thực hiện.

Nếu target.environment khác production, condition không đặt property deploy.enabled. Target deploy bị bỏ qua vì property không tồn tại.

Đây là một mẫu rất hữu ích: task condition chịu trách nhiệm đánh giá điều kiện boolean; target if chỉ kiểm tra property kết quả đã được đặt hay chưa.

### 4.1. Kết hợp nhiều điều kiện bằng and, or và not

Task condition hỗ trợ các điều kiện lồng nhau để biểu diễn logic phức tạp.

Ví dụ, chỉ cho phép deploy khi môi trường là production và property release.approved đã tồn tại:

~~~xml
<condition property="deploy.enabled">
    <and>
        <equals arg1="${target.environment}"
                arg2="production"
                casesensitive="false" />
        <isset property="release.approved" />
    </and>
</condition>

<target name="deploy" if="deploy.enabled">
    <echo message="Production release approved" />
</target>
~~~

Các điều kiện thường dùng:

- and: tất cả điều kiện con phải đúng.
- or: ít nhất một điều kiện con phải đúng.
- not: phủ định kết quả của điều kiện con.
- equals: so sánh hai giá trị.
- isset: kiểm tra một property có được thiết lập hay không.
- available: kiểm tra file, resource hoặc class có sẵn hay không, tùy cách cấu hình.

Ví dụ dùng or để cho phép build khi đang ở môi trường development hoặc khi có cờ cho phép thử nghiệm:

~~~xml
<condition property="build.allowed">
    <or>
        <equals arg1="${target.environment}" arg2="development" />
        <isset property="allow.experimental.build" />
    </or>
</condition>
~~~

Sau đó target có thể dùng if="build.allowed". Vì condition chỉ đặt property khi biểu thức đúng, cú pháp kiểm tra sự tồn tại ở target vẫn phù hợp.

### 4.2. Kiểm tra file tồn tại trước khi thực hiện target

Có thể dùng available để kiểm tra file đầu vào:

~~~xml
<condition property="config.present">
    <available file="config/production.properties" type="file" />
</condition>

<target name="load-production-config" if="config.present">
    <property file="config/production.properties" />
    <echo message="Production configuration loaded" />
</target>
~~~

Nếu file tồn tại, condition đặt config.present và target được chạy. Nếu không tồn tại, target bị bỏ qua.

Lưu ý rằng target có điều kiện vẫn có thể có dependency. Các dependency của nó được xử lý trước khi Ant đánh giá điều kiện thực hiện target. Nếu muốn tránh chạy một bước phụ thuộc khi điều kiện sai, cần đặt điều kiện phù hợp trên các target phụ thuộc hoặc tổ chức lại luồng gọi.

## 5. Khi nào dùng if="property", khi nào dùng if="${property}"?

Hãy chọn cú pháp dựa trên ý nghĩa của dữ liệu:

| Nhu cầu | Cách viết phù hợp | Ý nghĩa |
|---|---|---|
| Chỉ cần biết người dùng có khai báo tùy chọn hay không | if="verbose" | Chạy khi property verbose tồn tại, bất kể giá trị |
| Chỉ chạy khi cờ boolean là true | if="${feature.enabled}" | Chạy khi giá trị là true, on hoặc yes |
| Chạy khi cờ boolean là false | unless="${feature.enabled}" | Chạy khi giá trị là false, off hoặc no |
| Bỏ qua khi người dùng đã đặt cờ skip | unless="skip.tests" | Bỏ qua khi property skip.tests tồn tại, kể cả giá trị false |
| So sánh chuỗi với một giá trị cụ thể | condition kết hợp equals | Kiểm tra chính xác nội dung chuỗi |
| Kết hợp nhiều điều kiện | condition kết hợp and/or/not | Tính một kết quả boolean trước khi target chạy |

Ví dụ, hai cách khai báo sau có ý nghĩa khác nhau:

~~~xml
<target name="run-if-present" if="tests.enabled">
    <echo message="tests.enabled exists" />
</target>

<target name="run-if-true" if="${tests.enabled}">
    <echo message="tests.enabled is true-like" />
</target>
~~~

Nếu chạy:

~~~bash
ant -Dtests.enabled=false run-if-present
~~~

Target vẫn chạy vì tests.enabled tồn tại.

Nếu chạy:

~~~bash
ant -Dtests.enabled=false run-if-true
~~~

Target bị bỏ qua vì giá trị false được đánh giá là boolean false.

## 6. Dùng giá trị mặc định và tham số dòng lệnh

Có thể đặt mặc định trong buildfile, sau đó cho phép người gọi thay đổi bằng -D:

~~~xml
<project name="feature-build" default="build">
    <property name="feature.enabled" value="false" />

    <target name="build">
        <echo message="Building base application" />
    </target>

    <target name="feature" if="${feature.enabled}">
        <echo message="Building optional feature" />
    </target>

    <target name="all" depends="build,feature">
        <echo message="Build completed" />
    </target>
</project>
~~~

Mặc định, feature.enabled=false nên target feature bị bỏ qua. Khi gọi:

~~~bash
ant -Dfeature.enabled=true all
~~~

Ant nhận property từ dòng lệnh trước khi xử lý buildfile, nên khai báo mặc định trong buildfile không thay thế giá trị true đã truyền. Target feature được thực hiện.

Tương tự, có thể dùng:

~~~bash
ant -Dfeature.enabled=no all
~~~

để tắt tính năng.

Điều này phù hợp cho các cờ như debug.enabled, tests.enabled, integration.tests hoặc deploy.enabled. Nên quy định một tập giá trị nhất quán (true/false hoặc yes/no) để người gọi không truyền các chuỗi tùy ý khó hiểu.

## 7. Task-level if/unless namespaces từ Ant 1.9.1

Ngoài điều kiện ở cấp target, Ant 1.9.1 bổ sung namespace đặc biệt ant:if và ant:unless để điều khiển việc thực hiện task hoặc nested element.

Khai báo namespace trên project:

~~~xml
<project name="task-conditions"
         default="show"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="debug.enabled" value="false" />

    <target name="show">
        <echo if:set="debug.enabled"
              message="The debug property exists" />

        <echo if:true="${debug.enabled}"
              message="Debug mode is enabled" />

        <echo unless:true="${debug.enabled}"
              message="Debug mode is disabled" />
    </target>
</project>
~~~

Ba kiểu kiểm tra trong namespace:

| Cú pháp | Ý nghĩa |
|---|---|
| if:set="property" | Thực hiện khi property tồn tại |
| if:true="${property}" | Thực hiện khi giá trị biểu thức là true |
| if:blank="${property}" | Thực hiện khi giá trị null hoặc rỗng |
| unless:set="property" | Thực hiện khi property chưa tồn tại |
| unless:true="${property}" | Thực hiện khi giá trị biểu thức không true |
| unless:blank="${property}" | Thực hiện khi giá trị không rỗng |

Các namespace này áp dụng cho task và nested element. Chúng hữu ích khi chỉ một task hoặc một tham số cần điều kiện, thay vì phải tách toàn bộ công việc thành nhiều target.

Ví dụ, chỉ thêm tham số debug cho một lệnh exec:

~~~xml
<project name="conditional-argument"
         default="run"
         xmlns:if="ant:if"
         xmlns:unless="ant:unless">

    <property name="show.version" value="false" />

    <target name="run">
        <exec executable="java" failonerror="true">
            <arg value="-version" if:true="${show.version}" />
            <arg value="-X" unless:true="${show.version}" />
        </exec>
    </target>
</project>
~~~

Khi show.version=true, tham số -version được thêm. Khi giá trị là false, tham số -X được thêm. Ví dụ chỉ minh họa việc thêm tham số theo điều kiện; trong thực tế, hãy chọn tham số phù hợp với chương trình được gọi.

Không nhầm cú pháp namespace task-level với thuộc tính if="..." truyền thống của target. if:set kiểm tra sự tồn tại; if:true đánh giá giá trị boolean. Cả hai có tên gần giống nhau nhưng phục vụ hai câu hỏi khác nhau.

## 8. Lưu ý về dependency và target bị bỏ qua

Điều kiện if/unless của target chỉ quyết định các task bên trong target đó có được thực hiện hay không. Ant vẫn xử lý các target trong depends trước khi đánh giá điều kiện của target hiện tại.

Ví dụ:

~~~xml
<target name="prepare">
    <echo message="Prepare always runs" />
</target>

<target name="optional-build"
        depends="prepare"
        if="${feature.enabled}">
    <echo message="Optional build runs only when enabled" />
</target>
~~~

Khi chạy ant optional-build với feature.enabled=false, target prepare vẫn chạy. Target optional-build bị bỏ qua, nhưng dependency đã được xử lý trước đó.

Nếu muốn cả bước chuẩn bị cũng chỉ chạy khi feature bật, hãy đặt điều kiện tương ứng trên prepare hoặc tạo một target điều phối chỉ được gọi trong nhánh điều kiện đúng. Không nên giả định điều kiện ở target cha tự động truyền xuống toàn bộ dependency.

## 9. Những lỗi thường gặp

### 9.1. Dùng if="feature.enabled" để kiểm tra boolean

Đây là lỗi phổ biến nhất. Nếu property được đặt thành false, target vẫn chạy vì Ant chỉ kiểm tra sự tồn tại. Dùng if="${feature.enabled}" trên Ant 1.8.0 trở lên hoặc tính điều kiện bằng condition.

### 9.2. Dùng if="${mode}" để so sánh chuỗi

Nếu mode=production, giá trị production không phải boolean. Ant có thể xem nó như tên property cần kiểm tra. Dùng equals trong condition để so sánh mode với production.

### 9.3. Đặt condition với else="false" rồi dùng if="property"

Ví dụ:

~~~xml
<condition property="feature.enabled" value="true" else="false">
    <available file="feature.flag" />
</condition>

<target name="feature" if="feature.enabled">
    <echo message="Feature enabled" />
</target>
~~~

Nếu file feature.flag không tồn tại, condition đặt property feature.enabled thành false. Tuy nhiên, property vẫn tồn tại, nên if="feature.enabled" vẫn cho target chạy. Nếu dùng else="false", hãy kiểm tra boolean bằng if="${feature.enabled}" trên Ant 1.8.0 trở lên.

Một cách khác là bỏ thuộc tính else, để condition chỉ đặt property khi điều kiện đúng; khi sai, property không tồn tại và if="feature.enabled" sẽ bỏ qua target.

### 9.4. Dùng chuỗi rỗng như thể property chưa được đặt

Nếu property tồn tại với giá trị rỗng, if="property" vẫn xem nó là đã đặt. Muốn kiểm tra giá trị rỗng, dùng equals hoặc namespace if:blank thay vì kiểm tra sự tồn tại.

### 9.5. Quên phiên bản Ant

Property expansion cho if/unless có từ Ant 1.8.0. Namespace ant:if và ant:unless cho task và nested element có từ Ant 1.9.1. Nếu build cần chạy trên Ant cũ hơn, hãy dùng mẫu condition chỉ đặt property khi điều kiện đúng và target if="property".

### 9.6. Nghĩ rằng target bị bỏ qua thì dependency cũng bị bỏ qua

Các target trong depends chạy trước khi điều kiện target được đánh giá. Nếu một bước dependency không nên chạy khi feature tắt, hãy thiết kế điều kiện cho chính bước đó hoặc thay đổi cách điều phối.

## 10. Thực hành tốt

- **Đặt tên property thể hiện loại dữ liệu.** Dùng các tên như debug.enabled, tests.skip hoặc deploy.approved để người đọc biết mục đích.
- **Thống nhất giá trị boolean.** Chọn true/false hoặc yes/no; tránh dùng các chuỗi tùy ý.
- **Dùng kiểm tra tồn tại cho cờ hiện diện.** Nếu chỉ cần biết người gọi có truyền một property hay không, dùng if="name" hoặc unless="name".
- **Dùng property expansion cho boolean.** Trên Ant 1.8.0 trở lên, dùng if="${name}" hoặc unless="${name}" để đánh giá true-like/false-like.
- **Dùng condition cho logic tính toán.** Khi cần so sánh chuỗi, kiểm tra file hoặc kết hợp nhiều điều kiện, tạo property kết quả bằng condition.
- **Không đặt else="false" rồi kiểm tra sự tồn tại.** Nếu property luôn được đặt, target if="name" không thể phân biệt true với false.
- **Giữ điều kiện gần nơi cần áp dụng.** Dùng target condition khi toàn bộ target phụ thuộc vào cờ; dùng namespace task-level khi chỉ một task hoặc nested element cần điều kiện.
- **Kiểm soát dependency.** Nhớ rằng depends được xử lý trước khi điều kiện của target cha được đánh giá.
- **Ghi rõ phiên bản Ant tối thiểu.** Đặc biệt khi dùng property expansion hoặc namespace ant:if/ant:unless.

## 11. Kết luận

Trong Ant, if="property" và unless="property" theo cách viết truyền thống kiểm tra property có tồn tại hay không; chúng không tự hiểu giá trị false là chưa được thiết lập. Từ Ant 1.8.0, property expansion như if="${feature.enabled}" cho phép đánh giá các giá trị boolean phổ biến true/on/yes và false/off/no. Khi cần so sánh chuỗi hoặc kết hợp nhiều điều kiện, task condition là lựa chọn rõ ràng hơn. Từ Ant 1.9.1, namespace ant:if và ant:unless mở rộng cách áp dụng điều kiện đến task và nested element.

Hãy chọn cách kiểm tra theo đúng câu hỏi: property đã được cung cấp chưa, hay giá trị của nó có thực sự bật tính năng không. Phân biệt hai trường hợp này giúp buildfile hoạt động đúng khi nhận cấu hình từ dòng lệnh, file Properties và môi trường CI.

## Tài liệu tham khảo

- [Apache Ant Targets](https://ant.apache.org/manual/targets.html)
- [Apache Ant Properties — If/Unless Attributes](https://ant.apache.org/manual/properties.html)
- [Apache Ant If and Unless on Tasks and Nested Elements](https://ant.apache.org/manual/ifunless.html)
- [Apache Ant Condition Task](https://ant.apache.org/manual/Tasks/condition.html)

