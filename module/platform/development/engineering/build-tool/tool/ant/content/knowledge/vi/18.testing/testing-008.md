# Thiết lập timeout và kiểm soát dừng build khi kiểm thử thất bại

Trong Apache Ant, kiểm thử là một bước trong quy trình build. Một bộ test có thể chạy quá lâu do vòng lặp vô hạn, chờ dịch vụ bên ngoài hoặc deadlock; test cũng có thể kết thúc với assertion failure hay exception. Build cần có giới hạn thời gian và quy tắc rõ ràng để quyết định khi nào tiếp tục, khi nào dừng với trạng thái thất bại.

Với JUnit, task **junit** của Ant cung cấp hai nhóm điều khiển:

- **timeout** giới hạn thời gian chạy của test trong JVM được tách riêng (forked JVM).
- **haltonfailure**, **haltonerror**, **failureproperty** và **errorproperty** điều khiển cách Ant phản ứng với test failure hoặc error.

Cần kết hợp các thuộc tính này với cấu trúc target và dependency để kết quả kiểm thử quyết định trạng thái cuối cùng của build.

## 1. Task junit trong quy trình Ant

Task **junit** chạy test dùng framework JUnit. Ant cho phép khai báo một test class bằng phần tử **test** hoặc nhiều test class bằng **batchtest**.

Ví dụ một test class:

~~~xml
<junit printsummary="yes">
    <test name="com.example.ServiceTest"/>
</junit>
~~~

Ví dụ chạy nhiều test class theo pattern:

~~~xml
<junit printsummary="yes">
    <batchtest>
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

Trong quy trình thực tế, test cần classpath gồm class đã biên dịch, test class và thư viện JUnit. Task JUnit của Ant là optional task: cần có **ant-junit.jar** và **junit.jar** theo cách nạp thư viện mà phiên bản Ant đang dùng hỗ trợ. JUnit không được đóng gói mặc định trong mọi bản phân phối Ant.

Ví dụ classpath:

~~~xml
<junit>
    <classpath>
        <pathelement location="build/classes"/>
        <pathelement location="build/test-classes"/>
        <fileset dir="lib">
            <include name="junit*.jar"/>
            <include name="hamcrest*.jar"/>
        </fileset>
    </classpath>
    <!-- test hoặc batchtest -->
</junit>
~~~

Nếu Ant không nhận ra task **junit**, cần kiểm tra cách cài đặt hoặc nạp **ant-junit.jar**. Nếu task đã nhận nhưng không tìm thấy lớp JUnit, hãy kiểm tra JUnit runtime trong classpath.

Ant JUnit task hỗ trợ JUnit 3 và JUnit 4. Với dự án JUnit 5, hãy xem task **junitlauncher** và cấu hình engine tương ứng; không nên mặc định mọi tùy chọn của task junit cũ áp dụng nguyên xi cho junitlauncher.

## 2. Vì sao cần chạy test trong JVM riêng bằng fork

Thuộc tính **fork** quyết định test chạy trong JVM của Ant hay trong một JVM con:

~~~xml
<junit fork="true">
    <!-- test definitions -->
</junit>
~~~

Mặc định **fork="false"**, nghĩa là test chạy trong cùng JVM với Ant. Khi bật fork:

- Test chạy trong tiến trình Java riêng.
- Có thể giới hạn thời gian chạy bằng thuộc tính **timeout**.
- Test được cách ly tốt hơn khỏi trạng thái static hoặc system property của JVM Ant.
- Một test gọi **System.exit()** hoặc **Runtime.exit()** không kết thúc trực tiếp tiến trình Ant.
- Ant có thể kết thúc JVM con khi test vượt quá timeout.

Để sử dụng timeout của Ant, phải bật **fork="true"**. Nếu fork tắt, thuộc tính timeout bị bỏ qua.

### forkmode quyết định số JVM

Khi fork bật, thuộc tính **forkmode** quyết định cách Ant chia test vào các JVM:

| Giá trị | Cách chạy |
|---|---|
| **perTest** | Mỗi test class chạy trong một JVM riêng; đây là mặc định |
| **perBatch** | Mỗi phần tử batchtest chạy trong một JVM |
| **once** | Cố gắng chạy tất cả test trong một JVM |

Ngay cả khi đặt **once**, Ant vẫn có thể phải tạo nhiều JVM nếu các test có cấu hình không tương thích về các thuộc tính như haltonerror, haltonfailure, errorproperty, failureproperty hoặc filtertrace.

Fork tách biệt giúp giới hạn tiến trình và tránh một số dạng ảnh hưởng lẫn nhau giữa các test. Tuy nhiên, nó cũng có chi phí khởi tạo JVM; chọn forkmode theo cách tổ chức test và nhu cầu cách ly.

## 3. Thiết lập timeout bằng mili giây

Thuộc tính **timeout** của task junit nhận số mili giây:

~~~xml
<junit fork="true" timeout="60000">
    <test name="com.example.ServiceTest"/>
</junit>
~~~

Giá trị **60000** tương đương 60 giây. Nếu test execution vượt quá thời gian cho phép, Ant hủy việc chạy test trong JVM forked.

| Timeout | Thời gian |
|---:|---:|
| 5000 | 5 giây |
| 15000 | 15 giây |
| 60000 | 1 phút |
| 180000 | 3 phút |
| 300000 | 5 phút |

Chọn timeout dựa trên thời gian bình thường của bộ test, môi trường CI và thời gian chờ dịch vụ bên ngoài. Timeout quá ngắn có thể làm test hợp lệ thất bại khi CI tải cao; timeout quá dài khiến build treo lâu trước khi phát hiện vấn đề.

### Timeout phụ thuộc vào fork

Ví dụ sau có khai báo timeout nhưng không có tác dụng vì fork đang tắt:

~~~xml
<junit fork="false" timeout="30000">
    <batchtest>
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

Muốn Ant áp dụng giới hạn, cần bật fork:

~~~xml
<junit fork="true"
       timeout="30000"
       forkmode="perTest">
    <batchtest>
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

### Timeout không phải lúc nào cũng là thời gian riêng cho từng test method

Khi nhiều test chạy chung một JVM, timeout áp dụng cho tổng thời gian của nhóm test chạy trong JVM đó. Với **forkmode="once"**, toàn bộ test được gom vào một tiến trình nếu cấu hình cho phép; với **perBatch**, các test trong một batch chia sẻ tiến trình. Vì vậy, timeout không được hiểu là mỗi method luôn có một đồng hồ riêng.

Mặc định **perTest** tạo JVM cho từng test class. Nếu một class có nhiều method, giới hạn Ant vẫn áp dụng cho thời gian chạy của nhóm test trong JVM đó.

Nếu yêu cầu giới hạn chính xác cho từng method, dùng timeout do chính framework test hỗ trợ, ví dụ **@Test(timeout=...)** trong JUnit 4 hoặc **@Timeout** trong JUnit 5, đồng thời kiểm tra tương thích với phiên bản JUnit đang chạy.

### Điều gì xảy ra khi timeout?

Khi một forked test vượt thời gian, Ant kết thúc JVM con. Do JVM bị dừng cưỡng bức, phương thức dọn dẹp như **tearDown()** có thể không được gọi. Nếu test đang mở file, giữ lock, tạo container hoặc khởi động dịch vụ ngoài JVM, cần có bước cleanup độc lập ở quy trình build.

Timeout là cơ chế bảo vệ build khỏi một tiến trình test không kết thúc; nó không bảo đảm mọi tài nguyên do test tạo ra đều tự được giải phóng.

## 4. Dừng build ngay khi test thất bại bằng haltonfailure

Thuộc tính **haltonfailure** điều khiển việc dừng build nếu có test thất bại:

~~~xml
<junit fork="true"
       haltonfailure="true">
    <batchtest>
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

Khi có failure, task junit báo lỗi cho Ant và build dừng tại task đó. Các task tiếp theo trong target hoặc các target phụ thuộc phía sau không được chạy.

Mặc định **haltonfailure="false"**. Nếu không đặt thuộc tính này, Ant có thể ghi nhận test thất bại nhưng vẫn tiếp tục build. Điều đó có thể khiến pipeline kết thúc thành công nếu không có bước khác kiểm tra kết quả.

Nếu test là điều kiện bắt buộc trước khi đóng gói hoặc phát hành, cần bật **haltonfailure="true"** hoặc tự kiểm tra property kết quả và gọi task **fail** sau đó.

## 5. Phân biệt failure và error bằng haltonerror

JUnit phân biệt hai dạng kết quả:

- **Failure** thường là assertion không đạt, ví dụ expected bằng 10 nhưng actual bằng 8.
- **Error** thường là exception bất ngờ trong quá trình chạy test, ví dụ NullPointerException hoặc lỗi thiết lập test.

Thuộc tính **haltonerror** điều khiển việc dừng build khi có error:

~~~xml
<junit fork="true"
       haltonfailure="true"
       haltonerror="true">
    <!-- test definitions -->
</junit>
~~~

Cả hai thuộc tính đều mặc định tắt. Đặt rõ cả hai giúp người đọc thấy rằng build phải dừng khi có kết quả test không hợp lệ.

Lưu ý: tài liệu Ant mô tả **haltonfailure** là dừng khi test fail và errors cũng được tính là failures. Vì vậy, haltonfailure đã bao gồm error trong quy tắc failure; haltonerror là tùy chọn riêng để thể hiện và kiểm soát trường hợp error. Trong build fail-fast, thường đặt cả hai là true để chủ ý được rõ ràng.

Nếu cần chạy cleanup sau khi test kết thúc rồi mới đánh dấu build thất bại, không nên bật fail-fast ngay tại task junit. Khi đó có thể dùng failureproperty và errorproperty.

## 6. Ghi nhận kết quả bằng failureproperty và errorproperty

Thay vì dừng ngay, task junit có thể thiết lập property khi test gặp lỗi:

- **failureproperty**: tên property được thiết lập khi có failure. Error cũng được tính là failure.
- **errorproperty**: tên property được thiết lập khi có error.

Ví dụ:

~~~xml
<junit fork="true"
       timeout="60000"
       haltonfailure="false"
       haltonerror="false"
       failureproperty="tests.failed"
       errorproperty="tests.error">
    <test name="com.example.ServiceTest"/>
</junit>
~~~

Nếu test thất bại, Ant thiết lập **tests.failed**. Nếu test có error, Ant thiết lập thêm **tests.error**. Nếu không có kết quả tương ứng, property không được tạo.

Có thể kiểm tra kết quả bằng target có điều kiện:

~~~xml
<target name="report-test-failure" if="tests.failed">
    <echo message="One or more tests failed."/>
</target>
~~~

Hoặc gọi task fail:

~~~xml
<fail if="tests.failed"
      message="Build stopped because automated tests failed."/>
~~~

Task fail làm build kết thúc với trạng thái lỗi nếu property được chỉ định tồn tại.

### Property chỉ được thiết lập khi có sự kiện

Property chuẩn của Ant có tính chất chỉ thiết lập một lần. Không nên khai báo trước:

~~~xml
<property name="tests.failed" value="false"/>
~~~

rồi mong task junit đổi thành true. Vì property đã tồn tại, task junit không thể ghi đè giá trị đó theo cơ chế property thông thường.

Hãy để failureproperty và errorproperty tự tạo property khi có kết quả tương ứng. Đây cũng là lý do target **if="tests.failed"** hoạt động đúng: nó kiểm tra sự tồn tại của property, không kiểm tra chuỗi văn bản true/false.

## 7. Chạy cleanup rồi mới làm build thất bại

Một số quy trình cần luôn dọn môi trường test sau khi chạy, kể cả khi test thất bại. Ví dụ, build có thể khởi động một server tạm thời, chạy integration test rồi dừng server.

Nếu dùng **haltonfailure="true"**, task junit sẽ dừng build ngay khi test fail; task stop-server đặt phía sau có thể không được chạy.

Có thể ghi nhận lỗi, chạy cleanup, sau đó mới gọi fail:

~~~xml
<target name="integration-test">
    <antcall target="start-test-server"/>

    <junit fork="true"
           forkmode="perTest"
           timeout="120000"
           haltonfailure="false"
           haltonerror="false"
           failureproperty="tests.failed"
           errorproperty="tests.error">
        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
            <fileset dir="lib">
                <include name="junit*.jar"/>
                <include name="hamcrest*.jar"/>
            </fileset>
        </classpath>
        <formatter type="plain"/>
        <batchtest todir="build/reports">
            <fileset dir="build/test-classes">
                <include name="**/*IT.class"/>
            </fileset>
        </batchtest>
    </junit>

    <antcall target="stop-test-server"/>

    <fail if="tests.failed"
          message="Integration tests failed; see build/reports."/>
</target>
~~~

Trình tự:

1. Khởi động dịch vụ phục vụ kiểm thử.
2. Chạy integration test với timeout và ghi nhận kết quả.
3. Dừng dịch vụ.
4. Nếu có test failure hoặc error, task fail làm build thất bại.

Vì **failureproperty** bao gồm cả error, chỉ cần kiểm tra **tests.failed** nếu mọi lỗi test đều phải làm build thất bại. Có thể kiểm tra thêm **tests.error** để in thông báo riêng cho trường hợp error.

Mẫu này xử lý cleanup sau kết quả test thông thường, bao gồm test fail hoặc timeout được báo về từ JUnit task. Nếu chính task junit không thể khởi chạy do thiếu classpath, lỗi cấu hình hoặc lỗi khởi tạo nghiêm trọng, task có thể ném lỗi Ant trước khi các lệnh phía sau chạy. Với môi trường phức tạp, cần có cơ chế cleanup bên ngoài hoặc cấu trúc xử lý lỗi phù hợp cho cả lỗi khởi động test.

## 8. Kết hợp timeout, fail-fast và báo cáo trong target test

Ví dụ sau là một target test độc lập dùng batchtest, timeout, formatter và fail-fast:

~~~xml
<target name="test" depends="test-compile"
        description="Chạy toàn bộ JUnit test với giới hạn thời gian">

    <mkdir dir="build/reports"/>

    <junit printsummary="yes"
           fork="true"
           forkmode="perTest"
           timeout="60000"
           haltonfailure="true"
           haltonerror="true">

        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
            <fileset dir="lib">
                <include name="junit*.jar"/>
                <include name="hamcrest*.jar"/>
            </fileset>
        </classpath>

        <formatter type="plain"/>
        <formatter type="xml"/>

        <batchtest todir="build/reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>

    </junit>
</target>
~~~

Ý nghĩa:

- **depends="test-compile"** bảo đảm test class đã được biên dịch.
- **fork="true"** cho phép Ant áp dụng timeout bằng cách kiểm soát JVM con.
- **forkmode="perTest"** cô lập mỗi test class trong JVM riêng.
- **timeout="60000"** đặt giới hạn 60 giây cho thời gian chạy của JVM test tương ứng.
- **haltonfailure** và **haltonerror** làm build dừng khi có test không đạt.
- **formatter** tạo báo cáo plain text và XML trong thư mục reports.
- **batchtest** chọn các class có tên kết thúc bằng Test.class.

Nếu một test class cần hơn 60 giây vì phải khởi động môi trường tích hợp, hãy cân nhắc timeout riêng phù hợp hoặc chia nhóm test theo thời gian chạy. Không nên tăng timeout cho toàn bộ suite chỉ để che giấu một test bị treo.

## 9. Đưa kiểm thử thành điều kiện bắt buộc trước package

Chỉ tạo target test là chưa đủ; target package hoặc release cần phụ thuộc vào target test nếu quy trình yêu cầu kiểm thử thành công trước khi phát hành.

~~~xml
<target name="compile">
    <!-- Biên dịch mã nguồn chính -->
</target>

<target name="test-compile" depends="compile">
    <!-- Biên dịch mã nguồn kiểm thử -->
</target>

<target name="test" depends="test-compile">
    <!-- Chạy JUnit với timeout và haltonfailure -->
</target>

<target name="package" depends="test"
        description="Đóng gói sau khi kiểm thử thành công">
    <!-- Tạo JAR hoặc ZIP -->
</target>
~~~

Khi người dùng chạy **ant package**, Ant xử lý chuỗi phụ thuộc theo thứ tự:

~~~text
compile → test-compile → test → package
~~~

Nếu task junit dừng build do failure hoặc timeout, target package không được thực hiện. Đây là cách đưa kết quả test vào luồng điều phối của Ant thay vì chỉ dựa vào người dùng nhớ gọi target test.

Trong CI, nên gọi target cuối cùng có dependency tới test, ví dụ **ant package** hoặc **ant verify**. Nếu pipeline chỉ gọi **ant compile**, test có thể không được chạy.

## 10. Phân biệt timeout của Ant với timeout trong test framework

Có hai cấp timeout cần phân biệt:

| Cấp kiểm soát | Mục đích | Phạm vi |
|---|---|---|
| Ant JUnit task timeout | Ngăn JVM test chạy quá lâu | JVM forked; với nhiều test chung JVM, giới hạn áp dụng cho tổng thời gian của nhóm |
| Timeout của JUnit/test framework | Giới hạn thời gian của một test method hoặc đoạn kiểm thử | Theo cơ chế của phiên bản JUnit và annotation/API được dùng |

Với JUnit 4, một test method có thể dùng:

~~~java
@Test(timeout = 5000)
public void respondsWithinFiveSeconds() {
    service.respond();
}
~~~

Giới hạn này do JUnit xử lý ở cấp test method. Nó khác với timeout của Ant, vốn chỉ hoạt động khi fork và kiểm soát tiến trình test.

Với JUnit 5, có thể dùng annotation **@Timeout** khi chạy bằng JUnit Jupiter engine. Nếu dùng Ant, hãy chọn task và thư viện tương thích, thường là **junitlauncher** cho JUnit Platform, thay vì mặc định dùng task junit dành cho JUnit 3/4.

Kết hợp timeout cấp framework và timeout cấp tiến trình có thể tạo hai lớp bảo vệ: framework phát hiện method chạy quá lâu, còn Ant bảo vệ build trước trường hợp cả JVM test bị treo hoặc framework không thể tự kết thúc.

## 11. Đọc báo cáo và phân biệt các nguyên nhân build dừng

Build có thể dừng vì nhiều lý do:

- Assertion failure trong test.
- Exception bất ngờ trong test.
- Timeout khiến JVM forked bị kết thúc.
- Không tìm thấy class test hoặc thư viện JUnit.
- Lỗi khởi tạo JVM con hoặc lỗi cấu hình task.

Các trường hợp này cần được chẩn đoán khác nhau. Formatter plain/XML giúp xác định test nào fail và stack trace tương ứng; log Ant giúp xác định task có khởi chạy được JVM hay không.

Ví dụ, bật summary và báo cáo XML:

~~~xml
<junit printsummary="yes"
       fork="true"
       timeout="60000"
       haltonfailure="false"
       failureproperty="tests.failed">
    <formatter type="plain"/>
    <formatter type="xml"/>
    <test name="com.example.ServiceTest" todir="build/reports"/>
</junit>
~~~

Nếu build tiếp tục sau failure, hãy chắc chắn có bước kiểm tra **tests.failed** và gọi fail trước khi kết thúc target verify/package. Nếu không, pipeline có thể báo thành công dù báo cáo test chứa lỗi.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test treo nhưng timeout không có tác dụng | **fork** đang false | Bật **fork="true"** |
| Build dừng quá muộn | Timeout quá lớn hoặc test chạy chung JVM | Điều chỉnh timeout, dùng **forkmode="perTest"** khi cần cô lập |
| Mỗi test method không có timeout riêng | Timeout của Ant giới hạn JVM/group, không phải đồng hồ riêng cho từng method | Dùng timeout của JUnit framework cho từng method |
| Test thất bại nhưng build vẫn thành công | **haltonfailure** mặc định false và không kiểm tra property | Bật haltonfailure hoặc dùng failureproperty rồi gọi fail |
| Assertion fail nhưng cleanup không chạy | Fail-fast dừng tại task junit | Ghi nhận failure bằng property, cleanup rồi mới gọi fail |
| JVM bị dừng nhưng tearDown không chạy | Timeout kết thúc tiến trình forked | Dùng cleanup độc lập cho dịch vụ/tài nguyên bên ngoài |
| JUnit task không được nhận diện | Thiếu ant-junit.jar hoặc cấu hình task chưa đúng | Kiểm tra Ant optional libraries |
| Không tìm thấy test class | Thiếu test output hoặc classpath sai | Kiểm tra test-compile, classpath và pattern batchtest |
| Báo cáo không xuất hiện | Thiếu formatter hoặc thư mục đầu ra không hợp lệ | Khai báo formatter và tạo thư mục reports |
| Pipeline không dừng dù test fail | CI gọi target không phụ thuộc test | Đưa test vào dependency của verify/package hoặc gọi target test |

## 13. Nguyên tắc thiết kế

- Dùng **fork="true"** khi cần timeout cấp Ant hoặc cần cô lập JVM test.
- Đặt timeout theo đơn vị mili giây và chọn dựa trên thời gian thực tế của môi trường CI.
- Hiểu **forkmode** trước khi đặt timeout: nhiều test chung JVM sẽ dùng chung giới hạn thời gian tổng.
- Dùng **haltonfailure="true"** khi muốn fail-fast; đặt thêm **haltonerror="true"** để thể hiện rõ chính sách đối với test error.
- Dùng **failureproperty** và **errorproperty** khi cần cleanup hoặc thu thập báo cáo trước khi làm build thất bại.
- Không khai báo trước các property kết quả bằng chuỗi false vì property Ant không bị ghi đè theo cách thông thường.
- Đảm bảo target package/release phụ thuộc vào target test nếu test là điều kiện bắt buộc.
- Lưu báo cáo plain/XML để CI và developer biết test nào thất bại.
- Dùng timeout cấp JUnit cho từng method khi cần giới hạn chi tiết hơn timeout cấp JVM của Ant.
- Chuẩn bị cleanup độc lập cho tài nguyên bên ngoài vì JVM bị timeout có thể không chạy teardown.

Timeout bảo vệ quy trình khỏi test chạy quá lâu; các thuộc tính haltonfailure, haltonerror và property kết quả quyết định cách build phản ứng với test không đạt. Khi kết hợp đúng hai nhóm điều khiển này với target dependency, Ant có thể dừng đúng lúc, vẫn dọn được tài nguyên cần thiết và bảo đảm artifact chỉ được đóng gói sau khi kiểm thử thành công.

## Tài liệu tham khảo

- [Apache Ant — JUnit Task](https://ant.apache.org/manual/Tasks/junit.html)
- [Apache Ant — JUnitLauncher Task](https://ant.apache.org/manual/Tasks/junitlauncher.html)
- [Apache Ant — Fail Task](https://ant.apache.org/manual/Tasks/fail.html)

