# Chuyển hướng stdin, stdout và stderr trong Apache Ant

Khi dùng task <java> để chạy một chương trình Java trong buildfile, chương trình có thể nhận dữ liệu đầu vào, in kết quả thông thường và gửi thông báo lỗi. Ba luồng này tương ứng với standard input (stdin), standard output (stdout) và standard error (stderr).

Apache Ant cho phép điều khiển các luồng đó bằng các thuộc tính của task <java>:

- input hoặc inputstring cung cấp dữ liệu cho stdin.
- output hoặc outputproperty thu stdout về file hoặc property.
- error hoặc errorproperty tách stderr ra file hoặc property riêng.
- logError có thể đưa stderr vào log của Ant khi stdout đã được chuyển hướng.
- append quyết định ghi nối tiếp hay thay thế nội dung file đầu ra.

Để sử dụng I/O chuyển hướng một cách dự đoán được, trước hết cần hiểu tiến trình Java chạy trong JVM của Ant hay trong JVM riêng. Các ví dụ tương tác với stdin dưới đây dùng fork="true", vì Ant hỗ trợ gửi input đến JVM được fork.

## 1. Ba luồng chuẩn của một chương trình Java

Một chương trình Java thường giao tiếp với môi trường qua ba luồng:

| Luồng | Tên trong Java | Mục đích | Ví dụ |
|---|---|---|---|
| stdin | System.in | Nhận dữ liệu từ người dùng hoặc nguồn khác | Nhập tên, đọc một dòng lệnh |
| stdout | System.out | In kết quả bình thường | Kết quả xử lý, thông tin trạng thái |
| stderr | System.err | In cảnh báo và thông báo lỗi | Lỗi đầu vào, chẩn đoán |

Ví dụ chương trình Java đơn giản:

~~~java
package com.example;

import java.util.Scanner;

public class ConsoleApp {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);

        System.out.println("Enter a name:");
        String name = scanner.nextLine();

        System.out.println("Hello, " + name);
        System.err.println("DEBUG: greeting completed");
    }
}
~~~

Khi chạy từ terminal, người dùng nhập dữ liệu vào stdin. Dòng Hello được ghi ra stdout, còn thông báo DEBUG được ghi ra stderr.

Trong một build tự động, không nên phụ thuộc vào người dùng đang ngồi nhập dữ liệu ở terminal. Ant có thể lấy stdin từ một file hoặc từ chuỗi được khai báo trong buildfile; stdout và stderr cũng có thể được ghi vào file hoặc property để các bước tiếp theo sử dụng.

## 2. Chọn cách chạy chương trình: fork hay không fork

Task <java> có thể chạy lớp Java ngay trong JVM của Ant hoặc khởi chạy một JVM khác.

### 2.1. fork=false: chạy trong JVM của Ant

Mặc định, fork là false:

~~~xml
<java classname="com.example.ConsoleApp">
    <classpath location="build/classes" />
</java>
~~~

Lớp được gọi trong JVM đang chạy Ant. Cách này tránh tạo tiến trình mới và thường phù hợp với các chương trình đơn giản không cần tách môi trường chạy.

Tuy nhiên, nếu chương trình gọi System.exit() hoặc Runtime.exit(), việc chạy trong JVM Ant có thể ảnh hưởng đến chính tiến trình build. Tài liệu Ant khuyến nghị fork=true trong trường hợp đó.

### 2.2. fork=true: chạy trong JVM riêng

Khi fork=true, Ant khởi chạy một tiến trình JVM khác:

~~~xml
<java classname="com.example.ConsoleApp"
      fork="true">
    <classpath location="build/classes" />
</java>
~~~

Chế độ này phù hợp khi cần:

- Cung cấp stdin bằng file hoặc chuỗi.
- Chuyển stdout và stderr đến các đích riêng.
- Cấu hình JVM riêng bằng jvmarg hoặc maxmemory.
- Cô lập chương trình khỏi JVM đang điều phối Ant.
- Chạy chương trình có thể gọi System.exit().

Từ Ant 1.6.3, task <java> hỗ trợ tương tác với JVM được fork và gửi dữ liệu đầu vào cho nó bằng input hoặc inputstring.

## 3. Cung cấp stdin bằng thuộc tính input

Thuộc tính input chỉ định file mà chương trình Java sẽ đọc từ standard input.

Ví dụ, tạo file dữ liệu src/testdata/name.txt có nội dung:

~~~text
Lan
~~~

Buildfile:

~~~xml
<target name="run-from-file">
    <java classname="com.example.ConsoleApp"
          fork="true"
          input="src/testdata/name.txt">
        <classpath location="build/classes" />
    </java>
</target>
~~~

Khi chạy:

~~~bash
ant run-from-file
~~~

Chương trình ConsoleApp đọc dòng Lan từ System.in mà không cần người dùng nhập trực tiếp.

Thuộc tính input phù hợp khi dữ liệu đầu vào:

- Có nhiều dòng.
- Được dùng lại trong nhiều lần chạy.
- Là dữ liệu mẫu được lưu trong repository.
- Được tạo bởi một target trước đó.

Đường dẫn tương đối của input được phân giải theo basedir của project. Hãy bảo đảm file tồn tại trước khi task Java được thực hiện.

## 4. Cung cấp stdin bằng inputstring

Nếu dữ liệu đầu vào ngắn, có thể truyền trực tiếp qua inputstring:

~~~xml
<target name="run-from-string">
    <java classname="com.example.ConsoleApp"
          fork="true"
          inputstring="Lan">
        <classpath location="build/classes" />
    </java>
</target>
~~~

Chương trình đọc chuỗi Lan từ System.in.

Nếu chương trình gọi nextLine(), dữ liệu phải kết thúc bằng ký tự xuống dòng để nó nhận được một dòng hoàn chỉnh. Trong XML, có thể dùng ký tự tham chiếu &#10; để chèn newline:

~~~xml
<java classname="com.example.ConsoleApp"
      fork="true"
      inputstring="Lan&#10;">
    <classpath location="build/classes" />
</java>
~~~

### 4.1. input và inputstring loại trừ lẫn nhau

Không được khai báo đồng thời input và inputstring trong cùng một task <java>. Chọn một nguồn đầu vào:

~~~xml
<!-- Lấy stdin từ file -->
<java classname="com.example.ConsoleApp"
      fork="true"
      input="src/testdata/input.txt">
    <classpath location="build/classes" />
</java>

<!-- Hoặc lấy stdin từ chuỗi -->
<java classname="com.example.ConsoleApp"
      fork="true"
      inputstring="Lan&#10;">
    <classpath location="build/classes" />
</java>
~~~

Nếu không đặt input hoặc inputstring, stdin mặc định lấy từ console, trừ trường hợp spawn=true. Với build chạy trong CI hoặc chạy nền, nên cung cấp input rõ ràng cho chương trình không cần tương tác trực tiếp với người dùng.

### 4.2. Không đưa dữ liệu nhạy cảm vào inputstring

Giá trị inputstring được khai báo trong buildfile và có thể xuất hiện trong log hoặc lịch sử mã nguồn. Không nên dùng cách này để truyền mật khẩu, token hoặc khóa bí mật. Hãy sử dụng cơ chế quản lý secret của môi trường chạy và bảo đảm chương trình nhận dữ liệu theo cách phù hợp.

## 5. Chuyển hướng stdout bằng output

Thuộc tính output chỉ định file nhận standard output của chương trình Java.

~~~xml
<target name="run-and-save-output">
    <mkdir dir="build/logs" />

    <java classname="com.example.ConsoleApp"
          fork="true"
          inputstring="Lan&#10;"
          output="build/logs/app.stdout.log">
        <classpath location="build/classes" />
    </java>
</target>
~~~

Sau khi task hoàn tất, nội dung stdout được ghi vào build/logs/app.stdout.log.

Nếu không chỉ định error hoặc errorproperty riêng, stderr cũng được đưa vào cùng luồng output. Vì vậy, file output có thể chứa cả kết quả bình thường và thông báo lỗi.

Điều này hữu ích khi muốn lưu toàn bộ nội dung chương trình in ra vào một file. Nếu cần phân tích stdout và stderr riêng, hãy cấu hình thêm error.

## 6. Chuyển hướng stderr bằng error

Thuộc tính error chỉ định file nhận standard error:

~~~xml
<target name="run-with-separate-logs">
    <mkdir dir="build/logs" />

    <java classname="com.example.ConsoleApp"
          fork="true"
          inputstring="Lan&#10;"
          output="build/logs/app.stdout.log"
          error="build/logs/app.stderr.log">
        <classpath location="build/classes" />
    </java>
</target>
~~~

Kết quả:

- app.stdout.log chứa dữ liệu được ghi qua System.out.
- app.stderr.log chứa dữ liệu được ghi qua System.err.

Tách hai luồng giúp:

- Lưu kết quả chương trình mà không trộn cảnh báo và lỗi.
- Phân tích log lỗi riêng.
- Dùng stdout làm dữ liệu đầu vào cho bước xử lý tiếp theo.
- Giữ log dễ đọc khi chương trình in nhiều thông tin chẩn đoán.

Nếu chỉ đặt output mà không đặt error, Ant gộp stderr vào output. Nếu đặt cả hai, mỗi luồng được chuyển đến file tương ứng.

## 7. Thu stdout và stderr vào property

Thay vì ghi log ra file, Ant có thể lưu nội dung luồng vào property.

### 7.1. Dùng outputproperty

Thuộc tính outputproperty đặt tên property sẽ nhận stdout:

~~~xml
<java classname="com.example.VersionPrinter"
      fork="true"
      outputproperty="app.stdout">
    <classpath location="build/classes" />
</java>

<echo message="Program output: ${app.stdout}" />
~~~

Sau khi task Java hoàn tất, property app.stdout chứa nội dung đầu ra. Có thể dùng giá trị đó trong các task tiếp theo, chẳng hạn kiểm tra thông tin phiên bản hoặc tạo báo cáo.

Nếu stderr không được chuyển hướng riêng, nó cũng được gộp vào outputproperty. Điều này có nghĩa property có thể chứa cả thông tin lỗi.

### 7.2. Dùng errorproperty

Thuộc tính errorproperty lưu riêng stderr:

~~~xml
<java classname="com.example.ConsoleApp"
      fork="true"
      inputstring="Lan&#10;"
      outputproperty="app.stdout"
      errorproperty="app.stderr">
    <classpath location="build/classes" />
</java>

<echo message="STDOUT: ${app.stdout}" />
<echo message="STDERR: ${app.stderr}" />
~~~

Khi cả hai thuộc tính được đặt:

- app.stdout nhận nội dung System.out.
- app.stderr nhận nội dung System.err.

Đây là cách thuận tiện khi một target cần đọc kết quả và thông báo lỗi của chương trình để quyết định bước tiếp theo.

### 7.3. Property của Ant có tính bất biến

Property của Ant thông thường chỉ được thiết lập một lần. Nếu app.stdout đã có giá trị trước khi task chạy, outputproperty="app.stdout" không thay thế giá trị cũ.

Vì vậy:

- Dùng tên property riêng cho từng lần chạy nếu cần lưu nhiều kết quả.
- Không mong đợi outputproperty tự nối thêm vào property cũ.
- Nếu cần lưu nhiều lần chạy hoặc log dài, hãy chuyển hướng ra file và dùng append.
- Chỉ đọc property sau khi task Java đã hoàn tất.

## 8. Dùng logError khi muốn stderr xuất hiện trong log Ant

Nếu stdout đã được chuyển hướng ra file hoặc property, đôi khi vẫn muốn xem stderr ngay trong log của Ant.

Thuộc tính logError="true" phục vụ trường hợp đó:

~~~xml
<java classname="com.example.ConsoleApp"
      fork="true"
      inputstring="Lan&#10;"
      output="build/logs/app.stdout.log"
      logError="true">
    <classpath location="build/classes" />
</java>
~~~

Trong cấu hình này:

- stdout được ghi vào app.stdout.log.
- stderr được đưa vào log của Ant.
- stderr không được gộp vào file output.

Có một quy tắc quan trọng: nếu đã chuyển hướng stderr bằng error hoặc errorproperty, logError không có tác dụng. Hãy chọn một trong hai cách:

~~~xml
<!-- stderr vào file riêng -->
<java classname="com.example.ConsoleApp"
      fork="true"
      output="build/app.out"
      error="build/app.err">
    <classpath location="build/classes" />
</java>
~~~

Hoặc:

~~~xml
<!-- stdout vào file, stderr vào log Ant -->
<java classname="com.example.ConsoleApp"
      fork="true"
      output="build/app.out"
      logError="true">
    <classpath location="build/classes" />
</java>
~~~

Không nên bật logError khi kỳ vọng stderr đồng thời được ghi vào errorproperty. Hãy chọn nơi nhận stderr phù hợp với nhu cầu theo dõi.

## 9. Ghi nối tiếp hoặc ghi đè file bằng append

Thuộc tính append kiểm soát cách ghi các file output và error:

- append="false" là mặc định: file đầu ra cũ bị thay thế khi task ghi file.
- append="true": nội dung mới được nối vào cuối file.

Ví dụ ghi nối tiếp:

~~~xml
<java classname="com.example.BatchProcessor"
      fork="true"
      output="build/logs/batch.log"
      error="build/logs/batch-error.log"
      append="true">
    <classpath location="build/classes" />
</java>
~~~

Mỗi lần chạy, stdout được nối vào batch.log và stderr được nối vào batch-error.log.

Nếu append=false, nội dung file cũ được thay thế. Điều này phù hợp khi mỗi lần build cần một log mới để tránh nhầm lẫn với kết quả trước.

append áp dụng cho file output/error. Nó không làm property trở thành biến có thể thay đổi và không nối nội dung vào property outputproperty hoặc errorproperty.

Hãy quyết định chính sách log theo mục tiêu:

| Nhu cầu | Cấu hình |
|---|---|
| Mỗi lần chạy có log mới | append="false" |
| Ghi nhiều lần chạy vào cùng log | append="true" |
| Lưu stdout và stderr riêng | output và error |
| Thu nội dung để xử lý trong buildfile | outputproperty và errorproperty |

## 10. Kiểm tra mã thoát bằng resultproperty

Ngoài ba luồng chuẩn, chương trình còn trả về mã thoát (exit code). Theo quy ước thông thường:

- 0 biểu thị chương trình hoàn tất thành công.
- Khác 0 biểu thị chương trình kết thúc với trạng thái cần được xem xét.

Task <java> có thuộc tính resultproperty để lưu mã trả về vào property. Thuộc tính này có ý nghĩa khi fork=true và failonerror=false.

~~~xml
<java classname="com.example.Validator"
      fork="true"
      failonerror="false"
      resultproperty="validator.exit"
      output="build/logs/validator.out"
      error="build/logs/validator.err">
    <classpath location="build/classes" />
</java>

<echo message="Validator exit code: ${validator.exit}" />
~~~

Sau khi chương trình kết thúc, Ant lưu mã thoát vào validator.exit. Một target tiếp theo có thể dùng kết quả đó để quyết định bước xử lý.

Nếu đặt failonerror="true", mã thoát khác 0 khiến build thất bại. Trong trường hợp đó, resultproperty chỉ có thể nhận giá trị 0; task không tiếp tục bình thường để xử lý mã lỗi.

Ví dụ kiểm tra kết quả bằng condition:

~~~xml
<condition property="validator.success">
    <equals arg1="${validator.exit}" arg2="0" />
</condition>

<target name="report-success" if="validator.success">
    <echo message="Validation passed" />
</target>

<target name="report-failure" unless="validator.success">
    <echo message="Validation failed" />
</target>
~~~

Cần bảo đảm property validator.exit được thiết lập trước khi condition được đánh giá. Với những chương trình có thể không chạy hoặc bị timeout, hãy thiết kế xử lý lỗi rõ ràng thay vì giả định luôn có mã thoát hợp lệ.

## 11. Ví dụ tổng hợp: cung cấp stdin, tách stdout/stderr và lưu mã thoát

Giả sử một chương trình kiểm tra dữ liệu nhận nội dung từ file, in báo cáo ra stdout và ghi lỗi ra stderr. Buildfile có thể tổ chức như sau:

~~~xml
<project name="data-check" default="validate" basedir=".">
    <property name="classes.dir" location="build/classes" />
    <property name="input.file" location="src/testdata/request.txt" />
    <property name="logs.dir" location="build/logs" />

    <target name="prepare">
        <mkdir dir="${logs.dir}" />
    </target>

    <target name="validate" depends="prepare">
        <java classname="com.example.DataValidator"
              fork="true"
              input="${input.file}"
              output="${logs.dir}/validator.stdout.log"
              error="${logs.dir}/validator.stderr.log"
              append="false"
              failonerror="false"
              resultproperty="validator.exit">
            <classpath location="${classes.dir}" />
        </java>

        <echo message="Validator exit code: ${validator.exit}" />
    </target>
</project>
~~~

Luồng thực hiện:

1. Target prepare tạo thư mục log.
2. Task java khởi chạy DataValidator trong JVM riêng.
3. File request.txt được nối vào stdin của chương trình.
4. System.out được ghi vào validator.stdout.log.
5. System.err được ghi vào validator.stderr.log.
6. Mã thoát được lưu trong validator.exit.
7. Target có thể đọc mã thoát để quyết định tiếp tục hay báo lỗi.

Nếu muốn giữ log của nhiều lần chạy, thay append="false" bằng append="true". Nếu muốn stderr hiển thị ngay trong log Ant thay vì ghi file riêng, bỏ error và đặt logError="true".

## 12. spawn và giới hạn của I/O chuyển hướng

Task <java> có thuộc tính spawn để khởi chạy tiến trình có thể tiếp tục tồn tại sau khi Ant kết thúc. spawn yêu cầu fork=true.

Tuy nhiên, khi spawn=true, các thuộc tính input, output, error và resultproperty không thể sử dụng theo cách chuyển hướng I/O thông thường. Ant không chờ tiến trình hoàn tất để thu thập kết quả.

Ví dụ:

~~~xml
<java classname="com.example.BackgroundWorker"
      fork="true"
      spawn="true">
    <classpath location="build/classes" />
</java>
~~~

Cấu hình này phù hợp khi thực sự cần một tiến trình nền tồn tại độc lập. Nó không phù hợp với chương trình cần nhận stdin từ file, cần ghi stdout/stderr vào file do Ant quản lý hoặc cần đọc mã thoát trước khi build tiếp tục.

Nếu cần thu thập log và kết quả, giữ spawn=false (mặc định) để Ant theo dõi tiến trình đến khi hoàn tất.

Một tình huống cần lưu ý: khi chạy Ant như một tiến trình nền trên Unix-like (ví dụ ant &), nếu task java dùng fork=true và spawn=false, Ant có thể bị treo khi chương trình con cố đọc stdin từ console. Hãy cung cấp input hoặc inputstring rõ ràng cho chương trình không cần nhập tương tác.

## 13. Lỗi thường gặp khi chuyển hướng I/O

### 13.1. Khai báo input và inputstring cùng lúc

Hai thuộc tính loại trừ lẫn nhau. Hãy chọn file hoặc chuỗi, không dùng cả hai trong cùng task.

### 13.2. Chỉ chuyển hướng output nhưng quên stderr

Nếu không có error hoặc errorproperty riêng, stderr có thể được gộp vào output hoặc outputproperty. Nếu cần hai luồng tách biệt, khai báo cả hai đích.

### 13.3. Dùng logError cùng với error hoặc errorproperty

Khi stderr đã được chuyển hướng riêng bằng error hoặc errorproperty, logError không có tác dụng. Chọn ghi stderr vào file/property hoặc đưa nó vào log Ant.

### 13.4. Mong append nối nội dung vào property

append áp dụng cho file output và error. Property của Ant bất biến, nên không thể dùng append để cộng dồn kết quả vào một property đã có.

### 13.5. Dùng resultproperty khi spawn=true

spawn không tương thích với resultproperty. Nếu cần mã thoát, hãy để Ant chờ tiến trình hoàn tất bằng spawn=false.

### 13.6. Chương trình chờ stdin nhưng build không cung cấp dữ liệu

Nếu chương trình gọi Scanner hoặc BufferedReader trên System.in mà không có dữ liệu, tiến trình có thể chờ mãi. Dùng input hoặc inputstring, hoặc thiết kế chương trình để xử lý trường hợp không có dữ liệu.

### 13.7. Đọc outputproperty trước khi task chạy

Property đầu ra chỉ được thiết lập sau khi task Java hoàn tất. Đặt echo hoặc condition sau task java nếu cần sử dụng giá trị đó.

### 13.8. File log không được tạo vì thư mục cha chưa tồn tại

Trước khi ghi output hoặc error vào build/logs/app.log, hãy tạo thư mục build/logs bằng mkdir. Không giả định Ant tự tạo mọi thư mục cha cho file chuyển hướng.

## 14. Thực hành tốt

- **Tách stdout và stderr khi cần phân tích.** Dùng output và error hoặc outputproperty và errorproperty.
- **Dùng input file cho dữ liệu dài hoặc có thể tái sử dụng.** Dùng inputstring cho dữ liệu ngắn, không nhạy cảm.
- **Bật fork khi cần tương tác với JVM con.** Đặc biệt khi cần cung cấp stdin hoặc chạy chương trình có thể gọi System.exit().
- **Chọn append theo vòng đời log.** Ghi đè để có log riêng cho từng lượt; ghi nối tiếp khi muốn gom nhiều lần chạy.
- **Không nhầm logError với error.** logError đưa stderr vào log Ant; error chuyển stderr sang file riêng.
- **Dùng resultproperty khi cần kiểm tra mã thoát.** Kết hợp failonerror=false nếu build cần tiếp tục để xử lý kết quả khác 0.
- **Tránh spawn cho quy trình cần kết quả.** Tiến trình nền không phù hợp nếu build cần chờ, thu I/O hoặc đọc mã thoát.
- **Tạo thư mục log trước khi chạy.** Dùng mkdir để bảo đảm đường dẫn output/error tồn tại.
- **Không ghi secret vào inputstring hoặc log.** Quản lý dữ liệu nhạy cảm qua cơ chế secret của CI.
- **Đọc property sau task.** outputproperty, errorproperty và resultproperty được thiết lập khi task xử lý xong; property đã tồn tại không thể bị ghi đè theo cách thông thường.

## 15. Kết luận

Task <java> của Apache Ant có thể nhận stdin từ file qua input hoặc từ chuỗi qua inputstring; hai thuộc tính này không thể dùng đồng thời. stdout có thể được chuyển hướng bằng output hoặc outputproperty, còn stderr được tách riêng bằng error hoặc errorproperty. Nếu không tách stderr, nó có thể được gộp vào output. logError cho phép đưa stderr vào log Ant khi stdout đã được chuyển hướng và chưa cấu hình đích stderr riêng.

append quyết định ghi nối tiếp hay thay thế file log; resultproperty lưu mã thoát khi tiến trình được fork và failonerror=false. spawn=true phù hợp với tiến trình nền nhưng không tương thích với chuyển hướng I/O và thu mã kết quả thông thường. Khi xây dựng pipeline, hãy chọn đúng chế độ fork, cung cấp stdin rõ ràng, lưu riêng các luồng cần phân tích và kiểm tra mã thoát trước khi quyết định bước tiếp theo.

## Tài liệu tham khảo

- [Apache Ant Java Task](https://ant.apache.org/manual/Tasks/java.html)
- [Apache Ant I/O Redirector](https://ant.apache.org/manual/Types/redirector.html)
- [Apache Ant Exec Task](https://ant.apache.org/manual/Tasks/exec.html)

