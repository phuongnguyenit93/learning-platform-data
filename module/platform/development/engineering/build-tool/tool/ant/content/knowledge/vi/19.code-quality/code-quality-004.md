# Đo độ bao phủ kiểm thử bằng JaCoCo Ant Tasks

Độ bao phủ kiểm thử (test coverage) cho biết những phần nào của mã nguồn đã được thực thi khi chạy bộ kiểm thử. Trong Apache Ant, bạn có thể tích hợp **JaCoCo Ant Tasks** để thu thập dữ liệu thực thi, tạo báo cáo HTML/XML và đặt ngưỡng bao phủ cho quy trình build.

JaCoCo không thay thế framework kiểm thử như JUnit. JUnit thực thi các test case và kiểm tra kết quả; JaCoCo quan sát bytecode được chạy trong JVM, ghi dữ liệu bao phủ và tổng hợp dữ liệu thành báo cáo. Ant kết nối các bước này thành một quy trình có thể lặp lại:

~~~text
Biên dịch mã nguồn và test
          |
          v
Chạy test trong JVM có JaCoCo agent
          |
          v
Ghi dữ liệu thực thi (.exec)
          |
          v
Tạo báo cáo HTML / XML / CSV
          |
          v
Kiểm tra ngưỡng bao phủ
          |
          v
Build thành công hoặc thất bại theo quy tắc
~~~

## 1. Độ bao phủ kiểm thử là gì?

Khi chạy test, một số lớp, phương thức, câu lệnh và nhánh điều kiện được thực thi. Độ bao phủ đo phần mã đã được chạy so với tổng phần mã mà công cụ phân tích.

Ví dụ một lớp có phương thức:

~~~java
public class Discount {
    public double calculate(double price, boolean member) {
        if (member) {
            return price * 0.9;
        }
        return price;
    }
}
~~~

Nếu bộ test chỉ gọi phương thức với member = true, nhánh dành cho thành viên được chạy, nhưng nhánh còn lại chưa được chạy. Báo cáo có thể cho thấy dòng hoặc nhánh chưa được bao phủ.

Coverage giúp trả lời các câu hỏi:

- Test đã thực thi bao nhiêu dòng mã?
- Các nhánh điều kiện đã được kiểm tra đủ chưa?
- Phương thức hoặc lớp nào chưa được test chạm tới?
- Sau một thay đổi, mức bao phủ có giảm dưới ngưỡng của dự án không?

Coverage không chứng minh chương trình đúng. Một dòng có thể được thực thi mà kết quả không được kiểm tra. Vì vậy, cần đọc coverage cùng với chất lượng assertion, thiết kế test và các trường hợp biên.

## 2. JaCoCo và các thành phần chính

JaCoCo (Java Code Coverage) là công cụ đo độ bao phủ cho ứng dụng Java. JaCoCo hoạt động với bytecode đã biên dịch và có thể thu thập dữ liệu từ JVM đang chạy test hoặc ứng dụng.

Trong quy trình Ant, các thành phần thường dùng gồm:

| Thành phần | Vai trò |
|---|---|
| JaCoCo Ant JAR | Cung cấp các task JaCoCo cho build file. |
| jacoco:coverage | Bọc một task có fork JVM cùng JaCoCo Java agent để thu thập dữ liệu. |
| Execution data (.exec) | Lưu thông tin lớp và các probe đã được thực thi. |
| jacoco:report | Đọc execution data và class files để tạo báo cáo. |
| jacoco:check | So sánh coverage với các ngưỡng đã khai báo. |
| jacoco:merge | Gộp nhiều execution data file thành một file. |
| jacoco:dump | Lấy execution data từ JaCoCo agent đang chạy ở chế độ TCP server. |

Trong phần lớn build dự án, ba task quan trọng nhất là coverage, report và check.

### 2.1. Cài JaCoCo Ant Tasks vào build

Tải bản JaCoCo phù hợp với JDK và đặt file Ant integration, thường có tên dạng jacocoant.jar, vào thư mục công cụ của dự án, ví dụ:

~~~text
project/
├── build.xml
├── tools/
│   └── jacocoant.jar
├── src/
├── test/
└── build/
~~~

Khai báo namespace và taskdef ở đầu build file:

~~~xml
<project name="coverage-demo"
         default="coverage"
         basedir="."
         xmlns:jacoco="antlib:org.jacoco.ant">

    <property name="jacoco.ant.jar" location="tools/jacocoant.jar"/>

    <taskdef uri="antlib:org.jacoco.ant"
             resource="org/jacoco/ant/antlib.xml">
        <classpath>
            <pathelement location="${jacoco.ant.jar}"/>
        </classpath>
    </taskdef>

</project>
~~~

Ý nghĩa:

- xmlns:jacoco khai báo namespace cho các task JaCoCo.
- taskdef nạp định nghĩa task từ tài nguyên org/jacoco/ant/antlib.xml.
- classpath cho Ant biết vị trí JAR chứa các task.
- Các task được gọi bằng tiền tố jacoco:, ví dụ jacoco:coverage và jacoco:report.

JaCoCo Ant JAR phải có mặt khi Ant đọc build file. Nếu task báo không tìm thấy namespace hoặc không nạp được task, hãy kiểm tra đường dẫn JAR, phiên bản thư viện và cách khai báo namespace.

### 2.2. Phân biệt JaCoCo Ant JAR và JaCoCo agent

JaCoCo Ant JAR cung cấp task để điều khiển quy trình build. Agent là thành phần được gắn vào JVM để quan sát bytecode trong lúc chương trình chạy.

Khi dùng jacoco:coverage, task quản lý việc gắn agent cho JVM con được tạo bởi task lồng bên trong. Vì vậy, bạn thường không cần tự viết tùy chọn -javaagent khi sử dụng cách tích hợp này.

Không nhầm hai vai trò:

- JaCoCo Ant JAR giúp Ant hiểu các task JaCoCo.
- JaCoCo agent thu thập dữ liệu thực thi trong JVM.
- File .exec lưu kết quả để task report và check sử dụng.

## 3. Cấu hình thu thập coverage bằng jacoco:coverage

### 3.1. Task coverage bọc task chạy JVM

jacoco:coverage thường bọc một task Ant có khả năng khởi chạy JVM riêng, ví dụ java hoặc junit. JaCoCo agent được gắn vào JVM đó và ghi lại dữ liệu thực thi.

Ví dụ chạy một ứng dụng Java:

~~~xml
<jacoco:coverage destfile="build/coverage/app.exec">
    <java classname="com.example.Main"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
        </classpath>
    </java>
</jacoco:coverage>
~~~

Các điểm quan trọng:

- destfile chỉ định file nhận execution data.
- Task java phải chạy trong JVM được fork (fork="true") để agent được gắn vào tiến trình đó.
- failonerror="true" làm Ant báo lỗi nếu chương trình kết thúc với mã thoát khác 0.
- Classpath của chương trình vẫn được khai báo như cách chạy Java bình thường.

Với test JUnit, nguyên tắc tương tự: đặt task JUnit bên trong jacoco:coverage và bật fork cho JVM thực thi test.

### 3.2. Thu thập coverage khi chạy JUnit

Ví dụ:

~~~xml
<jacoco:coverage destfile="build/coverage/tests.exec">
    <junit fork="true"
           forkmode="once"
           printsummary="yes"
           haltonfailure="true">
        <classpath refid="test.classpath"/>
        <formatter type="plain"/>
        <batchtest todir="build/test-reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</jacoco:coverage>
~~~

Ở đây:

- fork="true" chạy test trong JVM riêng để JaCoCo agent có thể được gắn vào.
- forkmode="once" dùng một JVM cho lượt chạy test theo cấu hình này.
- classpath cung cấp lớp ứng dụng, lớp test và thư viện JUnit.
- batchtest tìm các lớp test theo mẫu.
- haltonfailure="true" làm build thất bại nếu test thất bại.

Nếu JUnit chạy trong nhiều JVM, mỗi JVM cần được cấu hình thu thập dữ liệu phù hợp. Hãy kiểm tra execution data sau khi chạy để chắc chắn mọi tiến trình test đều ghi vào vị trí mong muốn.

### 3.3. Chọn vị trí file execution data

Thông thường, file .exec được lưu trong thư mục build:

~~~xml
<property name="coverage.dir" location="build/coverage"/>
<property name="coverage.exec" location="${coverage.dir}/tests.exec"/>
~~~

Tạo thư mục trước khi chạy test:

~~~xml
<target name="prepare-coverage">
    <mkdir dir="${coverage.dir}"/>
</target>
~~~

Có thể cấu hình append trên task coverage:

~~~xml
<jacoco:coverage destfile="${coverage.exec}" append="false">
    <!-- Task test được bọc ở đây -->
</jacoco:coverage>
~~~

append="false" yêu cầu ghi dữ liệu cho lượt chạy này mà không nối tiếp dữ liệu cũ trong file. Cách này phù hợp với build sạch, nơi mỗi lượt test tạo một bộ execution data mới.

Nếu muốn tích lũy dữ liệu từ nhiều lần chạy, cần hiểu rõ dữ liệu nào thuộc cùng một phiên bản bytecode và chọn append hoặc merge có chủ đích. Không nên vô tình dùng dữ liệu cũ từ một lượt test khác để làm báo cáo của build hiện tại.

### 3.4. Một số tùy chọn thu thập dữ liệu

Task coverage có các tùy chọn điều khiển JaCoCo agent, thường gặp gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| destfile | File lưu execution data. |
| append | Có nối dữ liệu vào file đã có hay không. |
| sessionid | Gắn mã phiên vào dữ liệu thu thập. |
| dumponexit | Ghi dữ liệu khi JVM kết thúc. |
| output | Cách agent xuất dữ liệu, chẳng hạn ghi file hoặc giao tiếp TCP. |
| address, port | Địa chỉ và cổng dùng trong chế độ TCP. |
| includes, excludes | Lọc các lớp được instrument. |
| classdumpdir | Thư mục lưu bản dump của các lớp đã được agent xử lý. |

Đối với build thông thường, destfile và append thường đã đủ. Chỉ cấu hình chế độ TCP hoặc lọc lớp khi có nhu cầu cụ thể.

includes và excludes trên agent điều khiển lớp được instrument. Việc giới hạn lớp xuất hiện trong báo cáo còn có thể thực hiện bằng fileset trong phần classfiles của report. Hai bước lọc này phục vụ những mục đích khác nhau.

## 4. Tạo báo cáo bằng jacoco:report

Execution data chỉ là dữ liệu thô. Để xem coverage theo package, class, method và dòng mã, hãy dùng task jacoco:report.

### 4.1. Các nguồn dữ liệu cần cho report

Báo cáo JaCoCo cần ba nhóm thông tin:

1. **Execution data**: file .exec thu được khi chạy test.
2. **Class files**: bytecode đã biên dịch của ứng dụng cần phân tích.
3. **Source files**: mã nguồn để báo cáo HTML có thể hiển thị dòng mã.

Ví dụ:

~~~xml
<jacoco:report>
    <executiondata>
        <file file="build/coverage/tests.exec"/>
    </executiondata>

    <structure name="Coverage Demo">
        <classfiles>
            <fileset dir="build/classes"/>
        </classfiles>

        <sourcefiles encoding="UTF-8">
            <fileset dir="src/main/java"/>
        </sourcefiles>
    </structure>

    <html destdir="build/reports/jacoco/html"/>
    <xml destfile="build/reports/jacoco/jacoco.xml"/>
    <csv destfile="build/reports/jacoco/jacoco.csv"/>
</jacoco:report>
~~~

executiondata có thể nhận một hoặc nhiều file execution data. classfiles trỏ đến bytecode của mã ứng dụng. sourcefiles trỏ đến mã nguồn tương ứng. Các phần tử html, xml và csv chọn định dạng báo cáo cần tạo.

### 4.2. Báo cáo HTML

HTML phù hợp để lập trình viên mở bằng trình duyệt và xem chi tiết:

- Tổng quan coverage của toàn bộ bundle.
- Coverage theo package và class.
- Các method đã hoặc chưa được thực thi.
- Dòng mã được đánh dấu theo trạng thái coverage.
- Các nhánh điều kiện đã được thực thi hoặc còn thiếu.

Đường dẫn destdir là thư mục báo cáo HTML. Sau khi chạy target report, mở file index.html trong thư mục này.

Ví dụ:

~~~xml
<html destdir="build/reports/jacoco/html"/>
~~~

### 4.3. Báo cáo XML và CSV

XML thường được dùng bởi công cụ CI hoặc hệ thống phân tích chất lượng mã. CSV phù hợp khi cần nhập dữ liệu vào bảng tính hoặc xử lý bằng script.

~~~xml
<xml destfile="build/reports/jacoco/jacoco.xml"/>
<csv destfile="build/reports/jacoco/jacoco.csv"/>
~~~

Có thể tạo cả ba định dạng trong cùng một lần chạy report. Nếu chỉ cần báo cáo cho người phát triển, HTML có thể là đầu ra chính; nếu pipeline cần đọc coverage tự động, hãy xuất XML.

### 4.4. Class files phải khớp với bytecode đã được kiểm thử

JaCoCo liên kết execution data với lớp bằng thông tin nhận dạng bytecode. Nếu bạn biên dịch lại mã nguồn sau khi chạy test nhưng vẫn dùng file .exec cũ, dữ liệu có thể không khớp với class files mới.

Một quy trình an toàn là:

~~~text
Compile
  |
  v
Run tests with JaCoCo
  |
  v
Generate report from the same compiled classes
~~~

Không thay đổi hoặc ghi đè thư mục class đầu ra giữa bước test và report. Nếu cần build lại, hãy chạy lại test để tạo execution data tương ứng.

## 5. Hiểu các chỉ số coverage

JaCoCo cung cấp nhiều loại counter. Mỗi counter mô tả một góc nhìn khác nhau của mã được phân tích.

| Counter | Ý nghĩa |
|---|---|
| INSTRUCTION | Số lệnh bytecode đã thực thi. |
| LINE | Số dòng mã có thể thực thi đã được thực thi. |
| BRANCH | Các nhánh điều kiện, ví dụ nhánh true/false của if hoặc các nhánh switch. |
| COMPLEXITY | Độ phức tạp cyclomatic được bao phủ. |
| METHOD | Số method đã được thực thi. |
| CLASS | Số class có ít nhất một method được thực thi. |

Với mỗi counter, JaCoCo có thể báo:

- MISSEDCOUNT: số phần tử chưa được bao phủ.
- COVEREDCOUNT: số phần tử đã được bao phủ.
- TOTALCOUNT: tổng số phần tử.
- COVEREDRATIO: tỷ lệ đã bao phủ.
- MISSEDRATIO: tỷ lệ chưa bao phủ.

Ví dụ nếu có 80 dòng được bao phủ trên tổng 100 dòng, line coverage là 0.80, tương đương 80%.

### 5.1. Instruction coverage và line coverage

Instruction coverage dựa trên bytecode. Một dòng Java có thể tạo ra nhiều lệnh bytecode, do đó instruction coverage và line coverage không nhất thiết bằng nhau.

Line coverage dễ đọc với lập trình viên vì nó liên hệ trực tiếp với mã nguồn. Instruction coverage hữu ích khi muốn xem chi tiết mức thực thi ở cấp bytecode.

### 5.2. Branch coverage

Branch coverage đo các nhánh trong điều kiện và cấu trúc rẽ nhánh được JaCoCo nhận diện.

Ví dụ:

~~~java
if (amount > 100) {
    return amount * 0.9;
}
return amount;
~~~

Để bao phủ cả hai nhánh, test cần có ít nhất một trường hợp amount > 100 và một trường hợp không thỏa mãn điều kiện.

Một dòng có thể được tính là covered dù một nhánh trên dòng đó chưa được thực thi. Vì vậy, line coverage cao không đồng nghĩa branch coverage cũng cao.

### 5.3. Complexity coverage

Cyclomatic complexity phản ánh số đường đi độc lập trong luồng điều khiển của method. JaCoCo ước lượng mức complexity được bao phủ dựa trên các nhánh và method.

Chỉ số này có thể giúp nhận ra những method có nhiều nhánh nhưng ít test chạm tới. Nó không thay thế đánh giá thiết kế hoặc độ dễ bảo trì của mã.

### 5.4. Không đặt mục tiêu 100% một cách máy móc

Một số dòng có thể khó hoặc không cần test trực tiếp, ví dụ mã sinh tự động, mã chuyển tiếp đơn giản hoặc phần tích hợp phụ thuộc hệ thống bên ngoài. Mục tiêu coverage nên phản ánh rủi ro và giá trị của dự án.

Nên xem các dòng và nhánh chưa được bao phủ để quyết định có cần bổ sung test hay không. Không nên thêm test chỉ để tăng phần trăm mà không kiểm tra hành vi thực tế.

## 6. Đặt ngưỡng chất lượng bằng jacoco:check

Task jacoco:check giúp biến coverage thành một điều kiện của build. Nếu coverage thấp hơn ngưỡng đã định, task báo vi phạm và build có thể thất bại.

Ví dụ yêu cầu line coverage tối thiểu 80% và branch coverage tối thiểu 70% ở cấp bundle:

~~~xml
<jacoco:check>
    <executiondata>
        <file file="build/coverage/tests.exec"/>
    </executiondata>

    <rules>
        <rule element="BUNDLE">
            <limits>
                <limit counter="LINE"
                       value="COVEREDRATIO"
                       minimum="0.80"/>

                <limit counter="BRANCH"
                       value="COVEREDRATIO"
                       minimum="0.70"/>
            </limits>
        </rule>
    </rules>
</jacoco:check>
~~~

Ý nghĩa:

- element="BUNDLE" áp dụng quy tắc cho toàn bộ ứng dụng được phân tích.
- counter="LINE" chọn line coverage.
- counter="BRANCH" chọn branch coverage.
- value="COVEREDRATIO" yêu cầu kiểm tra tỷ lệ đã bao phủ.
- minimum="0.80" là mức tối thiểu 0.80, tương đương 80%.

Lưu ý: JaCoCo sử dụng tỷ lệ từ 0 đến 1 trong thuộc tính minimum, không phải số phần trăm từ 0 đến 100. Vì vậy, 75% được viết là 0.75.

### 6.1. Kiểm tra theo package hoặc class

Ngoài BUNDLE, rule có thể áp dụng cho cấp khác như PACKAGE, CLASS, SOURCEFILE hoặc METHOD tùy nhu cầu và phiên bản JaCoCo.

Ví dụ minh họa ngưỡng theo package:

~~~xml
<jacoco:check>
    <executiondata>
        <file file="build/coverage/tests.exec"/>
    </executiondata>

    <rules>
        <rule element="PACKAGE">
            <limits>
                <limit counter="LINE"
                       value="COVEREDRATIO"
                       minimum="0.75"/>
            </limits>
        </rule>
    </rules>
</jacoco:check>
~~~

Khi áp dụng rule ở cấp nhỏ, hãy cân nhắc các package hoặc class có ít dòng mã. Một lớp nhỏ có thể có tỷ lệ biến động mạnh chỉ vì một test bị thiếu. Có thể cần dùng rule giới hạn theo tổng số phần tử hoặc chọn phạm vi áp dụng phù hợp với cấu trúc dự án.

### 6.2. Chọn counter và ngưỡng hợp lý

Một quy tắc thường gặp:

- Dùng LINE để theo dõi mã nguồn đã được thực thi.
- Dùng BRANCH cho logic điều kiện quan trọng.
- Dùng METHOD hoặc CLASS để theo dõi phạm vi test ở cấp cấu trúc.
- Dùng COMPLEXITY khi muốn quan sát các đường đi độc lập.

Không nhất thiết đặt nhiều rule ngay từ đầu. Có thể bắt đầu bằng line coverage ở cấp bundle, sau đó bổ sung branch coverage cho phần logic có rủi ro cao.

### 6.3. Tích hợp check vào target verify

Nên đặt check thành target riêng:

~~~xml
<target name="check-coverage" depends="test">
    <jacoco:check>
        <executiondata>
            <file file="${coverage.exec}"/>
        </executiondata>
        <rules>
            <rule element="BUNDLE">
                <limits>
                    <limit counter="LINE"
                           value="COVEREDRATIO"
                           minimum="0.80"/>
                </limits>
            </rule>
        </rules>
    </jacoco:check>
</target>
~~~

Sau đó target verify có thể phụ thuộc vào cả report và check:

~~~xml
<target name="verify" depends="report,check-coverage">
    <echo message="Tests and coverage rules passed"/>
</target>
~~~

Nếu ngưỡng không đạt, jacoco:check làm bước verify thất bại theo quy tắc của task. Pipeline CI có thể dựa vào mã thoát của Ant để chặn việc đóng gói hoặc phát hành.

## 7. Gộp nhiều file execution data bằng jacoco:merge

Một dự án có thể chạy test thành nhiều nhóm, nhiều module hoặc nhiều tiến trình. Khi mỗi lượt tạo một file .exec, dùng jacoco:merge để gộp dữ liệu trước khi tạo báo cáo.

Ví dụ:

~~~xml
<jacoco:merge destfile="build/coverage/all-tests.exec">
    <fileset dir="build/coverage/parts">
        <include name="*.exec"/>
    </fileset>
</jacoco:merge>
~~~

Trong ví dụ:

- Thư mục build/coverage/parts chứa các file execution data đầu vào.
- destfile là file kết quả sau khi gộp.
- Report và check có thể đọc file đã gộp.

Tạo báo cáo từ dữ liệu gộp:

~~~xml
<jacoco:report>
    <executiondata>
        <file file="build/coverage/all-tests.exec"/>
    </executiondata>

    <structure name="All Test Suites">
        <classfiles>
            <fileset dir="build/classes"/>
        </classfiles>
        <sourcefiles encoding="UTF-8">
            <fileset dir="src/main/java"/>
        </sourcefiles>
    </structure>

    <html destdir="build/reports/jacoco/merged"/>
</jacoco:report>
~~~

Không đưa chính file đầu ra vào fileset đầu vào của merge. Hãy tách thư mục dữ liệu từng phần và file kết quả để tránh gộp lại dữ liệu cũ ngoài ý muốn.

## 8. Thu thập dữ liệu từ JVM chạy lâu bằng jacoco:dump

Với ứng dụng được khởi chạy độc lập hoặc chạy lâu trong môi trường kiểm thử, có thể cấu hình JaCoCo agent ở chế độ TCP server. Sau khi thực thi các kịch bản, task jacoco:dump kết nối đến agent để lấy execution data.

Một ví dụ cấu hình agent khi khởi chạy JVM độc lập:

~~~bash
java -javaagent:lib/jacocoagent.jar=output=tcpserver,address=127.0.0.1,port=6300,destfile=build/coverage/server.exec -jar app.jar
~~~

Sau khi ứng dụng đã chạy test hoặc kịch bản cần đo, Ant có thể lấy dữ liệu:

~~~xml
<jacoco:dump
    address="127.0.0.1"
    port="6300"
    destfile="build/coverage/server.exec"
    reset="true"/>
~~~

Task dump dùng để lấy dữ liệu từ agent TCP đang hoạt động. Cổng và địa chỉ phải khớp với cấu hình agent. Nếu JVM không chạy hoặc không mở TCP server, thao tác dump không thể kết nối.

Chế độ TCP hữu ích cho ứng dụng server hoặc kiểm thử tích hợp từ xa. Với test suite ngắn được Ant khởi chạy trực tiếp, jacoco:coverage thường đơn giản hơn.

## 9. Ví dụ hoàn chỉnh: Ant, JUnit và JaCoCo

Phần này kết hợp các bước biên dịch, chạy test, tạo báo cáo và kiểm tra ngưỡng trong một build file.

### 9.1. Cấu trúc project

Giả sử dự án có cấu trúc:

~~~text
coverage-demo/
├── build.xml
├── tools/
│   └── jacocoant.jar
├── lib/
│   ├── junit-4.13.2.jar
│   └── hamcrest-core-1.3.jar
├── src/
│   └── main/
│       └── java/
│           └── com/example/
│               └── Calculator.java
├── test/
│   └── java/
│       └── com/example/
│           └── CalculatorTest.java
└── build/
~~~

Thư mục lib chứa các JAR JUnit và Hamcrest dùng trong ví dụ. tools/jacocoant.jar là JaCoCo Ant integration tương thích với phiên bản JDK đang dùng.

### 9.2. Mã ứng dụng

File src/main/java/com/example/Calculator.java:

~~~java
package com.example;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("Divisor must not be zero");
        }
        return a / b;
    }
}
~~~

Lớp có phép cộng và phép chia. Phương thức divide có hai nhánh: chia bình thường và trường hợp mẫu số bằng 0.

### 9.3. Mã kiểm thử JUnit

File test/java/com/example/CalculatorTest.java:

~~~java
package com.example;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class CalculatorTest {

    @Test
    public void addsTwoNumbers() {
        Calculator calculator = new Calculator();
        assertEquals(7, calculator.add(3, 4));
    }

    @Test
    public void dividesTwoNumbers() {
        Calculator calculator = new Calculator();
        assertEquals(4, calculator.divide(20, 5));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsDivisionByZero() {
        Calculator calculator = new Calculator();
        calculator.divide(10, 0);
    }
}
~~~

Test kiểm tra kết quả của phép cộng, phép chia và trường hợp lỗi. Nhánh trong divide được thực thi ở cả hai trường hợp.

### 9.4. Build file hoàn chỉnh

File build.xml:

~~~xml
<project name="coverage-demo"
         default="verify"
         basedir="."
         xmlns:jacoco="antlib:org.jacoco.ant">

    <property name="src.dir" location="src/main/java"/>
    <property name="test.src.dir" location="test/java"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="test.classes.dir" location="build/test-classes"/>
    <property name="reports.dir" location="build/reports"/>
    <property name="coverage.dir" location="build/coverage"/>
    <property name="coverage.exec" location="${coverage.dir}/tests.exec"/>

    <property name="jacoco.ant.jar" location="tools/jacocoant.jar"/>
    <property name="junit.jar" location="lib/junit-4.13.2.jar"/>
    <property name="hamcrest.jar" location="lib/hamcrest-core-1.3.jar"/>

    <taskdef uri="antlib:org.jacoco.ant"
             resource="org/jacoco/ant/antlib.xml">
        <classpath>
            <pathelement location="${jacoco.ant.jar}"/>
        </classpath>
    </taskdef>

    <taskdef name="junit"
             classname="org.apache.tools.ant.taskdefs.optional.junit.JUnitTask">
        <classpath>
            <pathelement location="${ant.home}/lib/ant-junit.jar"/>
            <pathelement location="${junit.jar}"/>
        </classpath>
    </taskdef>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <pathelement location="${junit.jar}"/>
        <pathelement location="${hamcrest.jar}"/>
    </path>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${coverage.dir}"/>
        <mkdir dir="${reports.dir}/tests"/>
        <mkdir dir="${reports.dir}/jacoco"/>
    </target>

    <target name="compile" depends="prepare">
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false"/>
    </target>

    <target name="compile-tests" depends="compile">
        <javac
            srcdir="${test.src.dir}"
            destdir="${test.classes.dir}"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false">
            <classpath refid="test.classpath"/>
        </javac>
    </target>

    <target name="test" depends="compile-tests">
        <jacoco:coverage destfile="${coverage.exec}" append="false">
            <junit
                fork="true"
                forkmode="once"
                printsummary="yes"
                haltonfailure="true">
                <classpath refid="test.classpath"/>
                <formatter type="plain"/>
                <batchtest todir="${reports.dir}/tests">
                    <fileset dir="${test.classes.dir}">
                        <include name="**/*Test.class"/>
                    </fileset>
                </batchtest>
            </junit>
        </jacoco:coverage>
    </target>

    <target name="report" depends="test">
        <jacoco:report>
            <executiondata>
                <file file="${coverage.exec}"/>
            </executiondata>

            <structure name="Coverage Demo">
                <classfiles>
                    <fileset dir="${classes.dir}"/>
                </classfiles>
                <sourcefiles encoding="UTF-8">
                    <fileset dir="${src.dir}"/>
                </sourcefiles>
            </structure>

            <html destdir="${reports.dir}/jacoco/html"/>
            <xml destfile="${reports.dir}/jacoco/jacoco.xml"/>
            <csv destfile="${reports.dir}/jacoco/jacoco.csv"/>
        </jacoco:report>
    </target>

    <target name="check-coverage" depends="test">
        <jacoco:check>
            <executiondata>
                <file file="${coverage.exec}"/>
            </executiondata>
            <rules>
                <rule element="BUNDLE">
                    <limits>
                        <limit counter="LINE"
                               value="COVEREDRATIO"
                               minimum="0.80"/>
                        <limit counter="BRANCH"
                               value="COVEREDRATIO"
                               minimum="0.70"/>
                    </limits>
                </rule>
            </rules>
        </jacoco:check>
    </target>

    <target name="verify" depends="report,check-coverage">
        <echo message="Tests passed and coverage thresholds were met."/>
    </target>

</project>
~~~

Một số chi tiết cần lưu ý:

- Taskdef JaCoCo phải trỏ đúng JAR Ant integration.
- Taskdef JUnit cần ant-junit.jar và JUnit trên classpath của Ant.
- Test runtime classpath có cả lớp ứng dụng, lớp test, JUnit và Hamcrest.
- JaCoCo bọc task JUnit; JUnit được fork để agent chạy trong JVM thực thi test.
- Report phân tích build/classes, không lấy test classes làm phạm vi coverage của ứng dụng.
- Check dùng cùng file execution data với report.
- verify phụ thuộc vào report và check. Target test là dependency chung nên Ant chỉ cần thực hiện target đó một lần trong cùng lượt build.

Nếu cài Ant theo cách đã có sẵn task JUnit, hãy điều chỉnh taskdef cho phù hợp với môi trường. Đường dẫn JAR trong ví dụ cũng cần khớp với phiên bản thư viện thực tế.

### 9.5. Chạy build

Tại thư mục chứa build.xml:

~~~bash
ant clean
ant
~~~

Target mặc định là verify, nên Ant sẽ:

1. Tạo thư mục đầu ra.
2. Biên dịch mã ứng dụng.
3. Biên dịch mã test.
4. Chạy JUnit trong JVM được JaCoCo theo dõi.
5. Ghi build/coverage/tests.exec.
6. Tạo báo cáo HTML, XML và CSV.
7. Kiểm tra line và branch coverage theo ngưỡng.

Sau khi chạy thành công, mở:

~~~text
build/reports/jacoco/html/index.html
~~~

Nếu coverage thấp hơn ngưỡng, task check báo vi phạm và target verify không hoàn thành thành công. Bạn có thể mở HTML report để xem package, class, method hoặc dòng nào chưa được test thực thi.

Các target có thể gọi riêng:

~~~bash
ant compile
ant test
ant report
ant check-coverage
ant verify
~~~

Gọi ant report sẽ chạy dependency test trước nếu execution data chưa được tạo trong lượt build đó. Gọi ant check-coverage cũng yêu cầu test trước.

## 10. Lọc phạm vi lớp trong báo cáo

Một dự án thực tế có thể có mã sinh tự động, lớp adapter, mã test hoặc thư viện được đóng gói chung trong thư mục output. Bạn thường chỉ muốn đo mã ứng dụng do nhóm phát triển quản lý.

Có thể giới hạn class files trong report bằng fileset:

~~~xml
<classfiles>
    <fileset dir="${classes.dir}">
        <include name="com/example/service/**/*.class"/>
        <include name="com/example/domain/**/*.class"/>
        <exclude name="**/generated/**"/>
        <exclude name="**/*Config.class"/>
    </fileset>
</classfiles>
~~~

Fileset này quyết định những class files được đưa vào phân tích báo cáo. Nếu class bị loại khỏi report, coverage của nó cũng không được tính trong phạm vi report tương ứng.

Ngoài ra, JaCoCo agent có bộ lọc includes và excludes để điều khiển lớp được instrument. Hãy chỉ dùng bộ lọc agent khi cần giảm phạm vi thu thập hoặc tránh instrument một số lớp. Đừng loại lớp khỏi report chỉ để làm tỷ lệ tăng lên mà không ghi rõ phạm vi đo.

## 11. Một số vấn đề thường gặp

### 11.1. Không tìm thấy task jacoco:coverage

Nguyên nhân thường gặp:

- Đường dẫn jacocoant.jar sai.
- Taskdef chưa được khai báo.
- Namespace antlib:org.jacoco.ant không khớp.
- JAR JaCoCo không tương thích với môi trường Ant/JDK.

Hãy kiểm tra file JAR có tồn tại và taskdef được khai báo ở cấp project trước khi gọi task.

### 11.2. Không tạo ra file .exec

Kiểm tra:

- Task được bọc trong jacoco:coverage chưa.
- JVM thực thi có được fork không.
- destfile có trỏ đến thư mục tồn tại hoặc có thể tạo không.
- JVM có kết thúc bình thường để ghi dữ liệu khi dùng chế độ dump-on-exit không.
- Test có thực sự chạy trong tiến trình được JaCoCo theo dõi không.

Nếu test chạy trong tiến trình không được fork hoặc được khởi chạy từ một công cụ ngoài phạm vi task coverage, agent có thể không thu thập dữ liệu như mong đợi.

### 11.3. Báo cáo không có dữ liệu coverage

Một file .exec rỗng hoặc không có class phù hợp có thể làm báo cáo không hiển thị coverage hữu ích. Kiểm tra test có gọi mã ứng dụng không, đúng file execution data được đưa vào report chưa và class files có trùng với bytecode đã được kiểm thử không.

### 11.4. Báo cáo hiển thị lớp nhưng không có dòng mã

Report cần source files phù hợp để hiển thị mã nguồn. Kiểm tra đường dẫn sourcefiles, encoding và cấu trúc thư mục nguồn.

Line coverage cũng cần thông tin debug trong bytecode. Khi biên dịch bằng Ant javac, có thể bật debug="true" để giữ thông tin debug cần thiết.

### 11.5. Class files không khớp execution data

Nếu mã được biên dịch lại sau khi test, execution data cũ có thể không khớp với bytecode mới. Hãy clean, compile, test và report theo đúng thứ tự trong cùng một build.

### 11.6. Test thất bại nhưng vẫn có execution data

JaCoCo có thể ghi lại những lệnh đã chạy trước khi test thất bại. Điều đó không có nghĩa test suite thành công. Luôn để framework test báo lỗi và cấu hình Ant dừng build khi test thất bại, ví dụ bằng haltonfailure="true" và failonerror phù hợp.

Coverage chỉ mô tả mã đã chạy, không xác nhận assertion thành công.

### 11.7. Coverage thay đổi giữa các lần chạy

Một số nguyên nhân:

- Test được chạy ở các nhóm khác nhau.
- Test không xác định hoặc phụ thuộc thứ tự.
- Dữ liệu .exec cũ được nối vào file mới.
- Lớp được biên dịch khác nhau giữa test và report.
- Một phần test chạy trong JVM không được instrument.

Dùng clean hoặc tạo file execution data riêng cho mỗi build để dễ xác định nguồn dữ liệu. Nếu cần gộp nhiều lượt test, dùng jacoco:merge và ghi rõ phạm vi dữ liệu đầu vào.

### 11.8. Check thất bại dù report đã tạo

Report và check là hai task riêng. Report tạo đầu ra để xem; check áp dụng rule và có thể làm build thất bại. Hãy kiểm tra giá trị minimum, counter, element và execution data mà check đang sử dụng.

Tỷ lệ COVEREDRATIO dùng số thập phân từ 0 đến 1. Ví dụ 85% là 0.85, không phải 85.

## 12. Tích hợp JaCoCo vào CI

Trong pipeline CI, coverage thường là một bước sau khi test hoàn thành và trước khi đóng gói hoặc phát hành.

Một thứ tự hợp lý:

~~~text
Checkout
   |
   v
Clean
   |
   v
Compile
   |
   v
Run tests + JaCoCo
   |
   v
Generate reports
   |
   v
Check coverage threshold
   |
   v
Package / Publish
~~~

Ví dụ target:

~~~xml
<target name="ci" depends="verify">
    <jar destfile="build/dist/application.jar"
         basedir="${classes.dir}"/>
</target>
~~~

Nếu verify thất bại vì test hoặc coverage, Ant không tiếp tục target ci thành công. Điều này giúp ngăn artifact được đóng gói khi chất lượng test chưa đạt tiêu chuẩn đã thống nhất.

Nên lưu báo cáo HTML làm artifact để nhóm có thể mở và xem chi tiết. Báo cáo XML thường hữu ích cho hệ thống CI đọc và hiển thị xu hướng coverage.

Để so sánh giữa các lần chạy, hãy giữ cách chọn class files, source files, test suite và ngưỡng ổn định. Nếu thay đổi phạm vi đo, cần ghi rõ để tránh so sánh hai tỷ lệ được tính từ hai tập mã khác nhau.

## 13. Cách thiết lập ngưỡng coverage phù hợp

Không có một tỷ lệ duy nhất phù hợp với mọi dự án. Khi đặt ngưỡng, hãy cân nhắc:

- Mức độ quan trọng của module.
- Mức độ phức tạp và rủi ro của logic.
- Khả năng kiểm thử các thành phần phụ thuộc bên ngoài.
- Tỷ lệ mã sinh tự động hoặc mã tích hợp.
- Mức coverage hiện tại và khả năng cải thiện theo từng bước.

Với một codebase lâu năm có coverage thấp, có thể đặt ngưỡng ban đầu gần mức hiện tại rồi tăng dần khi thêm test. Với module mới, có thể đặt ngưỡng cao hơn ngay từ đầu.

Nên kết hợp line coverage và branch coverage cho logic quan trọng. Khi một nhánh chưa được thực thi, hãy xem đó là gợi ý để bổ sung test hoặc đánh giá xem nhánh đó có thể được loại bỏ hay không.

Đừng sửa hoặc xóa logic chỉ để đạt phần trăm coverage. Mục tiêu của JaCoCo là cung cấp bằng chứng về phạm vi thực thi, từ đó hỗ trợ quyết định cải thiện test.

## 14. Ghi nhớ

- **JaCoCo** đo độ bao phủ bytecode trong JVM; JUnit vẫn là framework thực thi và xác nhận test.
- **jacoco:coverage** bọc task như java hoặc junit để thu thập dữ liệu trong JVM được fork.
- **Execution data (.exec)** lưu thông tin thực thi, được dùng bởi report, check hoặc merge.
- **jacoco:report** tạo báo cáo HTML, XML và CSV từ execution data, class files và source files.
- **jacoco:check** đặt ngưỡng coverage và làm build thất bại khi có vi phạm.
- **jacoco:merge** gộp dữ liệu từ nhiều lượt test; **jacoco:dump** lấy dữ liệu từ agent TCP đang chạy.
- Các counter thường dùng là INSTRUCTION, LINE, BRANCH, COMPLEXITY, METHOD và CLASS.
- Giá trị COVEREDRATIO dùng thang từ 0 đến 1; 80% được khai báo là 0.80.
- Class files dùng để tạo report phải khớp bytecode đã được test; sourcefiles giúp hiển thị dòng mã.
- Coverage cao không tự chứng minh test tốt hoặc chương trình đúng. Hãy đọc những dòng và nhánh chưa được bao phủ cùng với assertion và rủi ro nghiệp vụ.

Khi kết hợp JaCoCo với Ant, bạn có thể tự động hóa việc thu thập coverage, xuất báo cáo cho lập trình viên và áp dụng ngưỡng chất lượng ngay trong quy trình build.

