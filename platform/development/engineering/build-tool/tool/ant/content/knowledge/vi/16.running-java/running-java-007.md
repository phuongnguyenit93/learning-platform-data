# Quản lý timeout, mã kết quả và failonerror

Khi dùng task `<java>` của Apache Ant để chạy một chương trình Java, build cần biết chương trình đã kết thúc hay chưa, kết thúc sau bao lâu và kết quả đó có được coi là thành công hay không. Nếu ứng dụng bị treo, chạy quá lâu hoặc trả về mã lỗi, Ant phải có cách xử lý phù hợp để pipeline không tiếp tục như thể mọi việc đã hoàn tất.

Ba thuộc tính quan trọng của task `<java>` là:

- `timeout`: giới hạn thời gian chạy của tiến trình Java được fork.
- `resultproperty`: lưu mã kết quả của tiến trình vào một Ant property.
- `failonerror`: yêu cầu Ant làm build thất bại khi chương trình trả về mã khác 0.

Các thuộc tính này thường được dùng cùng `fork="true"`, vì khi fork, chương trình chạy trong một tiến trình hệ điều hành riêng và Ant có thể quản lý thời gian chạy cũng như mã thoát của tiến trình đó.

## 1. Hiểu tiến trình Java mà Ant khởi chạy

Task `<java>` có thể chạy một lớp Java trong JVM của Ant hoặc tạo JVM riêng:

~~~xml
<target name="run-application">
    <java classname="com.example.Main">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Mặc định, `fork` là `false`. Khi đó lớp Java được chạy trong JVM đang thực thi Ant. Đây không phải một tiến trình hệ điều hành riêng để Ant thu thập mã thoát như một chương trình con. Lớp được chạy có thể chia sẻ trạng thái JVM với Ant, ví dụ system properties, static state, thread và tài nguyên đã nạp.

Nếu cần giới hạn thời gian, đọc mã thoát của chương trình hoặc cô lập ứng dụng khỏi JVM Ant, hãy bật fork:

~~~xml
<target name="run-application">
    <java classname="com.example.Main"
          fork="true">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Khi `fork="true"`, Ant khởi chạy một JVM con để chạy lớp được chỉ định. Ant có thể đợi tiến trình này kết thúc, kiểm tra mã thoát và áp dụng timeout.

| Chế độ | Cách chạy | Khả năng kiểm soát tiến trình |
|---|---|---|
| `fork="false"` | Chạy lớp trong JVM Ant | Không có mã thoát của một tiến trình con độc lập; timeout tiến trình không áp dụng |
| `fork="true"` | Khởi chạy JVM riêng | Có thể quản lý timeout, mã kết quả và cách xử lý mã thoát |
| `fork="true" spawn="true"` | Khởi chạy tiến trình tách rời | Ant không đợi kết quả hoàn tất và không thu được mã thoát |

Nếu một bước là điều kiện bắt buộc để build thành công, thông thường không nên dùng `spawn`, vì Ant không thể chờ và xác nhận công việc đó hoàn tất.

## 2. Giới hạn thời gian chạy bằng timeout

### 2.1. Ý nghĩa của timeout

Thuộc tính `timeout` đặt giới hạn thời gian cho tiến trình Java được fork. Đơn vị là mili giây (milliseconds), không phải giây.

Ví dụ, giới hạn ứng dụng chạy tối đa 60 giây:

~~~xml
<target name="run-with-timeout">
    <java classname="com.example.Main"
          fork="true"
          timeout="60000"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Trong ví dụ:

- `fork="true"` tạo JVM riêng.
- `timeout="60000"` đặt giới hạn 60.000 mili giây, tương đương 60 giây.
- `failonerror="true"` yêu cầu build thất bại nếu chương trình kết thúc với mã khác 0.

Khi hết thời gian mà tiến trình chưa kết thúc, Ant chấm dứt tiến trình được quản lý và báo lỗi timeout. Đây là tình huống khác với việc ứng dụng tự kết thúc và trả về mã lỗi thông thường.

### 2.2. Chọn thời gian phù hợp

Không nên đặt timeout quá ngắn chỉ để pipeline chạy nhanh. Một ứng dụng có thể cần thời gian khác nhau tùy dữ liệu, tải máy, môi trường mạng hoặc runner CI.

Có thể dùng property để quản lý giới hạn:

~~~xml
<property name="app.timeout.ms" value="120000" />

<target name="run-application">
    <java classname="com.example.Main"
          fork="true"
          timeout="${app.timeout.ms}"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Người gọi có thể thay đổi giới hạn cho một môi trường cụ thể:

~~~text
ant -Dapp.timeout.ms=300000 run-application
~~~

Ví dụ này đặt timeout thành 300.000 mili giây, tương đương 5 phút. Hãy thống nhất tên property và đơn vị trong dự án; hậu tố `.ms` giúp người đọc nhận biết giá trị đang tính bằng mili giây.

### 2.3. Timeout không phải thời gian chờ giữa các task

Timeout của task `<java>` giới hạn tiến trình Java được fork. Nó không đặt thời hạn tổng cho toàn bộ target hoặc toàn bộ build. Nếu một target chạy nhiều task, mỗi task có thời gian riêng; thời gian build tổng cộng có thể dài hơn timeout của một lần gọi Java.

Nếu cần giới hạn tổng thời gian của cả pipeline, hãy cấu hình timeout ở hệ thống CI hoặc bộ điều phối bên ngoài. Timeout ở CI và timeout trong task Java giải quyết hai phạm vi khác nhau:

- Timeout của task Java giới hạn một lần chạy ứng dụng.
- Timeout của CI giới hạn toàn bộ job hoặc bước pipeline theo chính sách runner.

### 2.4. Những giới hạn cần nhớ

Timeout chỉ có tác dụng khi Java được fork. Với `fork="false"`, lớp chạy trong JVM Ant nên Ant không thể kết thúc riêng một tiến trình con sau một khoảng thời gian.

Nếu ứng dụng tạo thêm các tiến trình con, việc chấm dứt JVM chính không nhất thiết bảo đảm mọi tiến trình con đều bị kết thúc trên mọi hệ điều hành. Nếu chương trình gọi công cụ bên ngoài hoặc tạo process tree, cần có cơ chế quản lý process tree ở ứng dụng hoặc hệ thống chạy.

Khi timeout xảy ra, hãy xem đó là lỗi thực thi cần điều tra. Không nên giả định ứng dụng đã hoàn tất bước dọn dẹp, ghi dữ liệu hoặc đóng tài nguyên như khi nó tự kết thúc bình thường.

## 3. Lấy mã kết quả bằng resultproperty

### 3.1. Mã thoát là gì?

Một tiến trình hệ điều hành thường kết thúc bằng một mã số. Theo quy ước phổ biến:

- `0`: chương trình hoàn tất thành công.
- Khác `0`: chương trình báo một dạng lỗi hoặc kết quả đặc biệt.

Ý nghĩa cụ thể của từng mã khác 0 do chính ứng dụng quy định. Ant nhận mã thoát của tiến trình Java fork và có thể lưu giá trị đó vào một property.

Ví dụ:

~~~xml
<target name="run-worker">
    <java classname="com.example.Worker"
          fork="true"
          failonerror="false"
          resultproperty="worker.exit.code">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>

    <echo message="Worker exit code: ${worker.exit.code}" />
</target>
~~~

Thuộc tính `resultproperty` chỉ có ý nghĩa khi `fork="true"`. Nếu không fork, lớp chạy trong JVM Ant và không có mã thoát của tiến trình con theo cách này.

Trong ví dụ, `failonerror="false"` cho phép target tiếp tục sau khi chương trình trả về mã khác 0 để build có thể đọc và xử lý kết quả. Đây cũng là giá trị mặc định của task Java, nhưng nên ghi rõ khi logic phía sau chủ động kiểm tra mã thoát.

### 3.2. Dùng mã kết quả để quyết định bước tiếp theo

Có thể kiểm tra mã thoát bằng task `<condition>` sau khi task Java hoàn tất:

~~~xml
<target name="run-and-check">
    <java classname="com.example.Worker"
          fork="true"
          failonerror="false"
          resultproperty="worker.exit.code">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>

    <condition property="worker.succeeded">
        <equals arg1="${worker.exit.code}" arg2="0" />
    </condition>

    <fail unless="worker.succeeded"
          message="Worker failed with exit code ${worker.exit.code}" />
</target>
~~~

Thứ tự thực thi rất quan trọng:

1. Ant khởi chạy Worker và đợi tiến trình kết thúc.
2. Mã thoát được ghi vào `worker.exit.code`.
3. Task condition so sánh mã đó với 0.
4. Nếu mã khác 0, property `worker.succeeded` không được tạo.
5. Task fail dừng build với thông báo chứa mã kết quả.

Đặt `condition` bên trong target sau task Java giúp nó được đánh giá sau khi tiến trình đã trả về. Nếu khai báo condition ở cấp project trước khi target chạy, giá trị mã thoát có thể chưa tồn tại tại thời điểm condition được đánh giá.

### 3.3. Xử lý nhiều mã kết quả

Một ứng dụng có thể định nghĩa nhiều mã thoát:

| Mã ví dụ | Ý nghĩa do ứng dụng quy định | Hướng xử lý có thể dùng |
|---|---|---|
| 0 | Thành công | Tiếp tục build |
| 1 | Lỗi chung | Dừng build |
| 2 | Tham số đầu vào không hợp lệ | Báo lỗi cấu hình |
| 10 | Không tìm thấy dữ liệu tùy chọn | Có thể bỏ qua nếu nghiệp vụ cho phép |
| 20 | Dịch vụ phụ trợ không sẵn sàng | Thử lại hoặc dừng theo chính sách |

Các mã trên chỉ là quy ước minh họa, không phải mã chuẩn của Ant. Build file phải dựa trên hợp đồng thực tế của chương trình được gọi.

Nếu chỉ có hai trạng thái thành công/thất bại, so sánh với 0 là đủ. Nếu cần phân biệt nhiều kết quả, hãy tạo các condition riêng hoặc gọi một bước xử lý chuyên biệt dựa trên mã trả về.

### 3.4. Lưu ý về tính bất biến của property

Ant property thông thường là bất biến: khi một property đã được thiết lập, khai báo sau không ghi đè giá trị cũ. Vì vậy, nếu cùng một build gọi chương trình nhiều lần và dùng lại một tên `resultproperty`, không nên giả định property sẽ được cập nhật như một biến thông thường.

Ví dụ, hai lần chạy cùng ghi vào `worker.exit.code` có thể khiến lần sau không thay đổi giá trị đã được thiết lập. Hãy dùng tên property riêng cho từng lần gọi hoặc thiết kế mỗi lần chạy trong một Ant invocation riêng. Điều này đặc biệt quan trọng khi xử lý nhiều module hoặc nhiều profile trong cùng một build.

## 4. Dùng failonerror để quyết định build có dừng hay không

### 4.1. Hành vi của failonerror

Thuộc tính `failonerror` điều khiển việc Ant có coi mã thoát khác 0 của tiến trình Java là lỗi làm build thất bại hay không.

~~~xml
<target name="run-required-task">
    <java classname="com.example.RequiredJob"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Khi chương trình trả về mã khác 0, task Java báo lỗi và Ant dừng build theo cơ chế lỗi thông thường.

Nếu đặt:

~~~xml
<java classname="com.example.OptionalJob"
      fork="true"
      failonerror="false">
    <classpath>
        <pathelement location="build/classes" />
    </classpath>
</java>
~~~

Ant không tự động làm build thất bại chỉ vì chương trình trả về mã khác 0. Build có thể tiếp tục, vì vậy người viết phải quyết định có cần kiểm tra mã thoát bằng `resultproperty` hay không.

### 4.2. Khi nào nên bật failonerror=true?

Dùng `failonerror="true"` khi bước Java là điều kiện bắt buộc của build, ví dụ:

- Chạy chương trình sinh mã nguồn mà kết quả là đầu vào cho bước biên dịch tiếp theo.
- Chạy công cụ kiểm tra chất lượng và cần dừng nếu kiểm tra thất bại.
- Thực thi migration hoặc bước chuẩn bị bắt buộc trước khi đóng gói.
- Chạy tác vụ tạo artifact mà nếu thất bại thì gói phát hành không hợp lệ.

Nếu chương trình thất bại mà các target sau vẫn tiếp tục, build có thể tạo ra artifact thiếu dữ liệu hoặc trạng thái không nhất quán.

### 4.3. Khi nào nên dùng failonerror=false?

Dùng `failonerror="false"` khi mã thoát cần được xử lý theo logic riêng, ví dụ:

- Một mã thoát có nghĩa là không có dữ liệu tùy chọn.
- Cần thu thập kết quả từ nhiều công cụ rồi tổng hợp báo cáo.
- Một bước kiểm tra có thể thất bại nhưng build vẫn cần lưu log hoặc kết quả chẩn đoán.
- Build cần phân biệt lỗi cấu hình, lỗi nghiệp vụ và trạng thái bỏ qua.

Khi đó, nên đặt `resultproperty` và kiểm tra giá trị ngay sau khi chương trình kết thúc. Không nên tắt failonerror rồi quên kiểm tra kết quả, vì build có thể báo thành công dù công việc quan trọng đã thất bại.

## 5. Kết hợp timeout, resultproperty và failonerror

Một task có thể dùng đồng thời ba thuộc tính:

~~~xml
<target name="run-validation">
    <java classname="com.example.ValidationJob"
          fork="true"
          timeout="90000"
          failonerror="true"
          resultproperty="validation.exit.code">
        <classpath>
            <pathelement location="build/classes" />
            <fileset dir="lib" includes="*.jar" />
        </classpath>
        <arg value="--mode" />
        <arg value="strict" />
    </java>
</target>
~~~

Ý nghĩa:

- Tiến trình Java được chạy trong JVM riêng.
- Ant giới hạn thời gian chạy ở 90.000 mili giây, tức 90 giây.
- Nếu tiến trình kết thúc với mã khác 0, build thất bại do failonerror.
- Nếu tiến trình kết thúc bình thường, mã kết quả được ghi vào property nếu property chưa được thiết lập.

Trong trường hợp này, `failonerror="true"` phù hợp khi mã khác 0 luôn là lỗi. Nếu cần xử lý một số mã đặc biệt, đặt failonerror thành false rồi kiểm tra resultproperty bằng condition hoặc logic khác.

Timeout là tình huống tiến trình bị chấm dứt do vượt giới hạn, không phải một mã thoát nghiệp vụ bình thường mà ứng dụng chủ động trả về. Hãy kiểm tra thông báo timeout riêng trong log.

## 6. Phân biệt lỗi ứng dụng, timeout và lỗi khởi chạy

Không phải mọi lỗi của task Java đều là cùng một loại. Khi đọc log, hãy phân biệt:

| Tình huống | Điều xảy ra | Hướng xử lý |
|---|---|---|
| Ứng dụng trả mã 0 | Tiến trình kết thúc thành công theo quy ước của ứng dụng | Tiếp tục build |
| Ứng dụng trả mã khác 0 | Ứng dụng báo lỗi hoặc trạng thái đặc biệt | Dùng failonerror hoặc resultproperty để xử lý |
| Quá timeout | Ant chấm dứt tiến trình vì vượt thời gian | Điều tra nguyên nhân chạy lâu, cân nhắc timeout phù hợp |
| Không khởi chạy được JVM | Thiếu executable, JDK sai hoặc lỗi tạo process | Kiểm tra JAVA_HOME, executable, quyền và môi trường |
| JVM khởi chạy nhưng lớp không tìm thấy | Classpath hoặc tên lớp không đúng | Kiểm tra classname, classpath và artifact |
| Lỗi trong JVM Ant khi không fork | Lớp chạy trong tiến trình Ant gặp exception hoặc thay đổi trạng thái | Xem stack trace và cân nhắc fork để cô lập |

`failonerror` chủ yếu quyết định phản ứng của Ant với mã thoát khác 0 từ chương trình fork. Khi không fork, lỗi Java như exception hoặc lỗi thực thi trong JVM Ant có thể được task báo trực tiếp; không nên kỳ vọng có một mã thoát process để kiểm tra bằng resultproperty.

Nếu JVM không khởi chạy được hoặc classpath sai, task có thể thất bại trước khi ứng dụng trả về mã thoát. Đây là lỗi khởi chạy hoặc cấu hình, không phải lỗi nghiệp vụ mà ứng dụng tự báo qua exit code.

## 7. Thu thập stdout và stderr khi chương trình chạy

Mã thoát cho biết kết quả ở mức tiến trình, nhưng log thường cần nội dung chi tiết để giải thích nguyên nhân. Task Java hỗ trợ các thuộc tính chuyển hướng output như `output`, `error`, `outputproperty`, `errorproperty` và `logError` tùy cách sử dụng.

Ví dụ ghi output ra tệp:

~~~xml
<target name="run-and-log">
    <java classname="com.example.BatchJob"
          fork="true"
          timeout="120000"
          failonerror="false"
          resultproperty="batch.exit.code"
          output="build/logs/batch-output.log"
          error="build/logs/batch-error.log">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Hãy tạo thư mục log trước khi chạy:

~~~xml
<mkdir dir="build/logs" />
~~~

Có thể đặt task mkdir trong target phụ thuộc của run-and-log để bảo đảm thứ tự.

Output và error giúp phân biệt thông báo thông thường với thông báo lỗi nếu chương trình ghi chúng vào các luồng tương ứng. Một số ứng dụng ghi mọi thứ vào stdout hoặc dùng logging framework ghi thẳng vào tệp riêng; khi đó cần cấu hình logging của ứng dụng để lưu đủ thông tin.

Không nên thu toàn bộ output rất lớn vào property nếu không cần thiết. Property tồn tại trong bộ nhớ Ant và phù hợp với dữ liệu nhỏ; với log dài, ghi ra tệp thường dễ quản lý hơn.

## 8. Tác động của spawn=true

Task Java có thuộc tính `spawn` để khởi chạy tiến trình tách rời:

~~~xml
<java classname="com.example.BackgroundService"
      fork="true"
      spawn="true">
    <classpath>
        <pathelement location="build/classes" />
    </classpath>
</java>
~~~

Khi spawn được bật:

- Ant khởi chạy tiến trình và không đợi chương trình kết thúc như cách fork thông thường.
- Không thể thu mã kết quả của tiến trình theo cách thông thường.
- Không thể sử dụng các cơ chế redirect output hoặc input của task theo cách thông thường.
- Ant không thể kiểm soát vòng đời chương trình như một bước build cần chờ hoàn tất.

Vì vậy, không dùng spawn cho bước biên dịch, kiểm thử, xác thực hoặc tạo artifact mà build cần biết kết quả trước khi tiếp tục. Nếu cần chạy service nền để kiểm thử tích hợp, hãy dùng một cơ chế quản lý vòng đời rõ ràng: khởi chạy service, chờ readiness, chạy test, rồi dừng service trong bước cleanup.

Không nên kết hợp spawn với kỳ vọng timeout hoặc resultproperty sẽ giám sát được tiến trình đến khi kết thúc. Khi cần timeout và mã thoát, dùng `fork="true"` mà không spawn.

## 9. Ví dụ hoàn chỉnh: chạy tác vụ, kiểm tra mã thoát và lưu log

Ví dụ sau chạy một chương trình kiểm tra dữ liệu. Chương trình có tối đa 2 phút, output và error được lưu riêng, và build thất bại nếu mã kết quả khác 0:

~~~xml
<project name="java-process-control" default="validate" basedir=".">

    <property name="build.dir" location="${basedir}/build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="logs.dir" location="${build.dir}/logs" />
    <property name="job.timeout.ms" value="120000" />

    <target name="prepare">
        <mkdir dir="${logs.dir}" />
    </target>

    <target name="validate" depends="prepare">
        <java classname="com.example.ValidationJob"
              fork="true"
              timeout="${job.timeout.ms}"
              failonerror="false"
              resultproperty="validation.exit.code"
              output="${logs.dir}/validation.out.log"
              error="${logs.dir}/validation.err.log">
            <classpath>
                <pathelement location="${classes.dir}" />
                <fileset dir="${basedir}/lib" includes="*.jar" />
            </classpath>
            <arg value="--strict" />
        </java>

        <condition property="validation.succeeded">
            <equals arg1="${validation.exit.code}" arg2="0" />
        </condition>

        <fail unless="validation.succeeded"
              message="Validation failed with exit code ${validation.exit.code}. See ${logs.dir}." />
    </target>

</project>
~~~

Quy trình:

1. Target prepare tạo thư mục log.
2. Ant khởi chạy ValidationJob trong JVM riêng.
3. Tiến trình được giới hạn ở 120.000 mili giây.
4. stdout và stderr được ghi ra hai tệp.
5. Ant lưu mã kết quả vào validation.exit.code.
6. Condition xác định mã kết quả có bằng 0 hay không.
7. Task fail dừng build nếu validation không thành công.

Trong ví dụ này, failonerror được đặt false vì build muốn tự kiểm tra mã kết quả và tạo thông báo riêng. Nếu mọi mã khác 0 đều là lỗi và không cần xử lý đặc biệt, có thể đặt failonerror true và bỏ condition/resultproperty.

Nếu tiến trình vượt timeout hoặc không thể khởi chạy, task Java có thể thất bại trước khi phần condition chạy. Khi đó, đọc thông báo Ant và log đã được tạo để phân biệt timeout với mã lỗi do ứng dụng trả về.

## 10. Xử lý nhiều bước Java trong cùng build

Khi build gọi nhiều chương trình, nên đặt tên property và log theo từng bước:

~~~xml
<target name="run-importer">
    <java classname="com.example.Importer"
          fork="true"
          timeout="60000"
          failonerror="false"
          resultproperty="importer.exit.code">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>

<target name="run-validator" depends="run-importer">
    <java classname="com.example.Validator"
          fork="true"
          timeout="90000"
          failonerror="false"
          resultproperty="validator.exit.code">
        <classpath>
            <pathelement location="build/classes" />
        </classpath>
    </java>
</target>
~~~

Đây là ví dụ về cách đặt tên property riêng cho từng bước. Trong build thực tế, cần xác định chính sách khi importer trả mã lỗi: nếu validator không được chạy khi import thất bại, hãy kiểm tra importer.exit.code và dùng fail trước khi sang target validator.

Không tái sử dụng một resultproperty chung cho nhiều lần gọi trong cùng một Ant project, vì property không hoạt động như biến có thể cập nhật. Tên riêng giúp log và thông báo lỗi chỉ ra đúng chương trình.

Nếu các bước có thể chạy độc lập, có thể thiết kế target tổng hợp để chạy lần lượt và thu thập trạng thái. Nếu một bước là prerequisite của bước sau, hãy biểu diễn quan hệ bằng `depends` và kiểm tra kết quả trước khi thực hiện bước tiếp theo.

## 11. Quyết định dùng failonerror hay resultproperty

| Nhu cầu | Cấu hình gợi ý | Lý do |
|---|---|---|
| Mã khác 0 luôn phải làm build thất bại | `fork="true" failonerror="true"` | Ant dừng ngay khi chương trình báo lỗi |
| Cần in mã thoát rồi mới dừng | `failonerror="false" resultproperty="..."` và `<fail>` sau đó | Build kiểm soát thông báo lỗi |
| Có mã thoát đặc biệt được phép tiếp tục | `failonerror="false" resultproperty="..."` và condition theo từng mã | Có thể phân biệt trạng thái nghiệp vụ |
| Chương trình có thể bị treo | `fork="true" timeout="..."` | Ant giới hạn thời gian chạy |
| Chạy service nền không cần chờ kết quả | `fork="true" spawn="true"` | Ant trả quyền điều khiển sau khi khởi chạy |
| Cần biết chương trình nền đã sẵn sàng chưa | Không dựa vào spawn đơn thuần | Cần health check hoặc readiness probe riêng |

Khi lựa chọn, hãy hỏi: build có cần chờ chương trình kết thúc không? Có cần mã thoát không? Nếu mã khác 0, có được phép tiếp tục không? Có giới hạn thời gian không? Câu trả lời xác định tổ hợp thuộc tính phù hợp.

## 12. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Timeout không có tác dụng | Chưa bật `fork="true"` hoặc timeout được đặt sai đơn vị | Bật fork và nhập timeout bằng mili giây |
| Build tiếp tục dù chương trình trả mã khác 0 | `failonerror="false"` và không kiểm tra resultproperty | Bật failonerror hoặc kiểm tra mã thoát rồi dùng fail |
| Không có resultproperty | Chưa fork, tiến trình không kết thúc bình thường hoặc property đã được thiết lập trước | Kiểm tra fork, vòng đời process và dùng tên property mới |
| Mã kết quả lần chạy sau không đổi | Ant property bất biến, tên resultproperty đã có giá trị | Dùng property riêng cho từng lần gọi hoặc Ant invocation riêng |
| Build dừng trước khi condition kiểm tra mã thoát | failonerror đang bật hoặc lỗi timeout/khởi chạy | Dùng failonerror=false nếu cần tự xử lý mã bình thường; điều tra timeout riêng |
| Output không được ghi vào tệp | Thư mục đích chưa tồn tại, task spawn hoặc ứng dụng ghi log riêng | Tạo thư mục trước, không spawn và kiểm tra cấu hình logging |
| Tiến trình con vẫn chạy sau timeout | Ứng dụng tạo process con hoặc service tách rời | Quản lý process tree/service ở ứng dụng hoặc hệ thống chạy |
| Build báo lỗi dù lớp Java chạy đúng | Exception trong JVM Ant, classpath sai hoặc lỗi khởi chạy | Xem stack trace, phân biệt fork và in-process |
| Build không đợi ứng dụng kết thúc | Đã bật spawn | Tắt spawn nếu kết quả là điều kiện để build tiếp tục |

Khi xử lý sự cố, hãy xem log của Ant cùng stdout/stderr của ứng dụng. Mã thoát chỉ cho biết kết quả tổng quát; thông báo lỗi chi tiết thường nằm trong log của chương trình hoặc stack trace.

## 13. Nguyên tắc vận hành ổn định

- Dùng `fork="true"` khi cần timeout hoặc mã thoát của một tiến trình độc lập.
- Nhập timeout bằng mili giây và chọn giới hạn phù hợp với môi trường.
- Dùng `failonerror="true"` khi mã khác 0 luôn là lỗi làm build thất bại.
- Dùng `resultproperty` cùng `failonerror="false"` khi cần phân tích mã thoát trước khi quyết định.
- Kiểm tra resultproperty ngay sau task Java; nhớ rằng Ant property là bất biến.
- Phân biệt timeout, lỗi khởi chạy JVM và mã lỗi do ứng dụng tự trả về.
- Không dùng spawn cho bước mà build cần đợi, kiểm tra output hoặc thu mã thoát.
- Ghi stdout/stderr ra tệp khi cần chẩn đoán, và tạo thư mục log trước.
- Quản lý process con và service nền bằng cơ chế vòng đời riêng.
- Kiểm tra mã thoát của toàn bộ lệnh Ant trong CI để pipeline nhận đúng trạng thái build.

Quản lý timeout, mã kết quả và failonerror giúp build Ant phản ánh chính xác trạng thái của chương trình Java được gọi. Khi tiến trình được fork có giới hạn thời gian, mã thoát được kiểm tra và lỗi được xử lý có chủ đích, các target phía sau chỉ chạy khi điều kiện cần thiết đã được đáp ứng.

