# Giới hạn điều khiển luồng của Ant lõi và khi cần phần mở rộng

Apache Ant được thiết kế chủ yếu để mô tả và thực thi các bước build thông qua target, dependency và task. XML của Ant có thể biểu diễn nhiều quy trình có điều kiện, nhưng Ant lõi không phải một ngôn ngữ lập trình tổng quát với đầy đủ cấu trúc `if/else`, vòng lặp và `switch` như Java.

Khi build script cần rẽ nhánh hoặc lặp, trước hết hãy tận dụng các cơ chế sẵn có như `depends`, `if`, `unless`, task `<condition>`, các selector và những task có thể xử lý cả một tập file. Khi yêu cầu thực sự cần cấu trúc điều khiển phong phú, có thể dùng phần mở rộng như Ant-Contrib, viết custom task hoặc chọn một công cụ build phù hợp hơn.

## 1. Ant lõi điều khiển quy trình bằng target và dependency

Một target là một nhóm công việc có tên. Thuộc tính `depends` xác định target nào phải hoàn tất trước target hiện tại.

```xml
<project name="sample" default="package" basedir=".">
    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <jar destfile="dist/app.jar" basedir="build/classes"/>
    </target>
</project>
```

Khi chạy `ant package`, Ant thực hiện `init`, rồi `compile`, sau đó mới `package`. Đây là cơ chế điều khiển luồng cơ bản và thường là đủ cho một build tuyến tính.

Ant lõi phù hợp với những quan hệ như:

- Bước A phải hoàn tất trước bước B.
- Một nhóm target dùng chung bước chuẩn bị.
- Một target chỉ chạy khi property đã được đặt hoặc chưa được đặt.
- Nhiều file được xử lý cùng một task thông qua `fileset`, `path` hoặc resource collection.

Khi dependency graph rõ ràng, người đọc có thể nhìn vào `build.xml` để hiểu thứ tự build mà không phải lần theo một đoạn mã điều khiển phức tạp.

## 2. Điều kiện cơ bản bằng if và unless trên target

Ant lõi cho phép khai báo `if` hoặc `unless` trên target:

```xml
<target name="publish" if="publish.enabled">
    <echo message="Publishing artifact"/>
</target>

<target name="skip-publish" unless="publish.enabled">
    <echo message="Publishing is disabled"/>
</target>
```

- `if="publish.enabled"` cho phép chạy các task trong target nếu property `publish.enabled` đã tồn tại.
- `unless="publish.enabled"` cho phép chạy các task trong target nếu property đó chưa tồn tại.

Điều kiện cổ điển của target kiểm tra sự tồn tại của property, không kiểm tra giá trị boolean bên trong property. Nếu property được đặt thành chuỗi `false`, `if` vẫn được xem là đạt vì property đã tồn tại.

Một giới hạn quan trọng về thứ tự: nếu target có `depends`, dependency chạy trước khi Ant kiểm tra `if` hoặc `unless` của target đó. Vì vậy, target bị bỏ qua vẫn có thể đã làm các dependency chạy xong. Chỉ đặt những công việc thực sự bắt buộc chung vào dependency; đặt công việc riêng của từng nhánh bên trong target có điều kiện.

## 3. Tạo nhánh if/else bằng target và condition

Ant lõi không có task `if/else` tổng quát để đặt tùy ý giữa các task. Tuy nhiên, có thể biểu diễn hai nhánh bằng property được tạo bởi `<condition>`, sau đó dùng hai target có `if` và `unless`.

```xml
<project name="environment-build" default="dispatch" basedir=".">
    <property name="environment" value="dev"/>

    <target name="prepare">
        <condition property="is.production">
            <equals arg1="${environment}" arg2="production"/>
        </condition>
    </target>

    <target name="build-production" depends="prepare" if="is.production">
        <echo message="Building production configuration"/>
        <!-- Các task chỉ dành cho production đặt tại đây. -->
    </target>

    <target name="build-development" depends="prepare" unless="is.production">
        <echo message="Building non-production configuration"/>
        <!-- Các task dành cho dev/test đặt tại đây. -->
    </target>

    <target name="dispatch" depends="build-production,build-development"/>
</project>
```

Chạy với môi trường mặc định:

```bash
ant dispatch
```

Target `build-development` chạy. Target `build-production` bị bỏ qua vì property `is.production` chưa được đặt.

Chạy production:

```bash
ant -Denvironment=production dispatch
```

Target `prepare` đặt `is.production`; sau đó target production chạy và target development bị bỏ qua.

Trong ví dụ, `prepare` là dependency chung. Các task của từng nhánh nằm bên trong target tương ứng, nên chúng chỉ chạy khi điều kiện của nhánh đạt. Không thêm các bước riêng của production vào `depends` của `build-production` nếu muốn chúng được bỏ qua khi môi trường không phải production.

Ant property là bất biến. Giá trị `environment` truyền bằng `-D` có thể ghi đè default được khai báo trong build file vì user property có độ ưu tiên cao; một property đã được đặt thì lần khai báo sau không thay đổi được nó. Dùng property đầu vào riêng và property kết quả như `is.production` giúp luồng điều kiện dễ hiểu.

## 4. Dùng task condition để kiểm tra nhiều loại điều kiện

Task `<condition>` đặt một property khi biểu thức lồng bên trong đúng. Ant có nhiều điều kiện con, ví dụ:

- `<equals>` so sánh hai giá trị.
- `<isset>` kiểm tra property có tồn tại.
- `<available>` kiểm tra file, thư mục hoặc resource có sẵn.
- `<and>`, `<or>`, `<not>` kết hợp hoặc đảo điều kiện.
- `<contains>` kiểm tra một chuỗi trong giá trị văn bản.

Ví dụ chỉ cho phép đóng gói khi file cấu hình tồn tại và môi trường là `production`:

```xml
<target name="prepare-release">
    <condition property="release.ready">
        <and>
            <equals arg1="${environment}" arg2="production"/>
            <available file="config/production.properties" type="file"/>
        </and>
    </condition>
</target>

<target name="release" depends="prepare-release" if="release.ready">
    <jar destfile="dist/app.jar" basedir="build/classes"/>
</target>
```

`condition` không chạy một nhánh task tùy ý. Nó đánh giá biểu thức và tạo property. Target có điều kiện sử dụng property đó để quyết định có chạy các task của mình hay không.

Nếu muốn dừng build khi điều kiện không đạt thay vì bỏ qua target, kết hợp `<condition>` với `<fail>`:

```xml
<target name="validate-release">
    <condition property="release.ready">
        <and>
            <equals arg1="${environment}" arg2="production"/>
            <available file="config/production.properties" type="file"/>
        </and>
    </condition>

    <fail unless="release.ready"
          message="Release requires environment=production and config/production.properties."/>
</target>
```

Sự khác biệt về ý nghĩa: target có `if` không đạt thì phần việc của target được bỏ qua; `<fail>` được kích hoạt thì toàn bộ build dừng với trạng thái thất bại.

## 5. Không phải mọi lần lặp đều cần vòng lặp

Một nhầm lẫn phổ biến là cố tạo vòng lặp XML để xử lý từng file. Nhiều task Ant đã nhận được một tập tài nguyên và tự xử lý từng phần tử trong tập đó.

Ví dụ, không cần viết một target riêng cho từng file resource:

```xml
<target name="copy-resources">
    <copy todir="build/resources">
        <fileset dir="src/main/resources">
            <include name="**/*"/>
            <exclude name="**/*.local.properties"/>
        </fileset>
    </copy>
</target>
```

Task `copy` xử lý tất cả file được chọn bởi fileset. Tương tự:

- `<delete>` có thể xóa một fileset.
- `<checksum>` có thể tính checksum cho nhiều file trong một resource collection.
- `<jar>` và `<zip>` có thể đóng gói nhiều file.
- `<javac>` có thể biên dịch tập source được chọn.
- `<apply>` có thể áp dụng một lệnh bên ngoài lên tập file phù hợp.

Hãy ưu tiên task xử lý tập tài nguyên khi công việc là một thao tác đồng nhất trên nhiều file. Cách này thường ngắn gọn và dễ bảo trì hơn việc tự viết vòng lặp để gọi lại cùng một task.

## 6. Những khả năng Ant lõi có nhưng không thay thế ngôn ngữ lập trình

Ant lõi có một số cấu trúc hỗ trợ tổ chức công việc:

| Cơ chế | Công dụng | Giới hạn cần nhớ |
|---|---|---|
| `depends` | Sắp xếp thứ tự giữa các target | Không phải câu lệnh rẽ nhánh tùy ý |
| `if` / `unless` trên target | Bật hoặc bỏ qua task của target theo sự tồn tại property | Không kiểm tra trực tiếp giá trị boolean; dependency chạy trước điều kiện |
| `<condition>` | Đánh giá biểu thức và đặt property | Chỉ tạo kết quả điều kiện, không chứa một khối task tùy ý |
| `<fail>` | Dừng build khi điều kiện không đạt | Dừng cả lần build hiện tại |
| `<antcall>` | Gọi target khác trong cùng build file | Tạo ngữ cảnh project mới cho lần gọi; lạm dụng làm luồng khó theo dõi |
| `<subant>` | Gọi target trên nhiều build file con | Dùng để điều phối build con, không phải vòng lặp task tổng quát |
| `<macrodef>` | Đóng gói chuỗi task có tham số để tái sử dụng | Không tự cung cấp cấu trúc if/else hoặc vòng lặp tổng quát |
| `<parallel>` | Chạy các nhánh công việc độc lập đồng thời | Không dùng thay cho điều kiện; phải quản lý xung đột output và tài nguyên |

Những cơ chế này đủ cho nhiều build script có luồng tuyến tính, một vài nhánh theo môi trường và các thao tác trên tập file. Khi logic bắt đầu có nhiều trạng thái, lặp lồng nhau hoặc xử lý lỗi theo nhánh, việc mô phỏng bằng hàng loạt target có thể khiến build khó đọc.

## 7. Dùng antcall để gọi một target sau khi nhánh đã được chọn

Task `<antcall>` gọi một target khác trong cùng project. Có thể đặt nó bên trong target có điều kiện để chỉ gọi phần việc chung khi nhánh đó được chọn.

```xml
<project name="dispatch-build" default="dispatch" basedir=".">
    <property name="environment" value="dev"/>

    <target name="prepare">
        <condition property="is.production">
            <equals arg1="${environment}" arg2="production"/>
        </condition>
    </target>

    <target name="build-production" depends="prepare" if="is.production">
        <antcall target="build-common">
            <param name="artifact.suffix" value="prod"/>
        </antcall>
    </target>

    <target name="build-development" depends="prepare" unless="is.production">
        <antcall target="build-common">
            <param name="artifact.suffix" value="dev"/>
        </antcall>
    </target>

    <target name="build-common">
        <echo message="Building artifact for ${artifact.suffix}"/>
    </target>

    <target name="dispatch" depends="build-production,build-development"/>
</project>
```

Target `build-common` chỉ được gọi từ nhánh đã thỏa điều kiện. Phần `<param>` truyền property cho lần gọi target con.

`antcall` có chi phí và ngữ nghĩa riêng: nó thực hiện target trong một project context mới, mặc định kế thừa các property của project gọi và có thể truyền thêm property bằng `param`. Không nên dùng `antcall` để thay thế mọi quan hệ `depends`. Với bước bắt buộc theo thứ tự, `depends` thường rõ ràng hơn. Dùng `antcall` khi thực sự cần gọi lại một target như một nhánh có tham số.

## 8. Khi nào Ant lõi bắt đầu trở nên khó dùng?

Hãy xem xét một yêu cầu build như sau:

- Đọc danh sách mười môi trường.
- Với từng môi trường, chọn một bộ cấu hình.
- Nếu môi trường là production, chạy thêm bước ký artifact.
- Nếu kiểm thử thất bại, ghi nhận lỗi rồi chuyển sang môi trường tiếp theo.
- Cuối cùng tạo một báo cáo tổng hợp.

Ant lõi có thể thực hiện nhiều phần trong yêu cầu này bằng target, condition, antcall và task xử lý tập tài nguyên. Nhưng khi phải lặp qua danh sách, rẽ nhánh lồng nhau và tiếp tục sau lỗi theo từng phần tử, build file có thể trở nên dài và khó theo dõi.

Các dấu hiệu cho thấy đã đến lúc cần phần mở rộng hoặc công cụ khác:

1. Có nhiều vòng lặp lồng nhau hoặc cần duyệt danh sách giá trị động.
2. Có nhiều nhánh `if/else` bên trong cùng một nhóm task.
3. Cần `switch/case`, `while`, `try/catch` hoặc xử lý lỗi theo từng phần tử.
4. Phải dùng nhiều `antcall` chỉ để mô phỏng cấu trúc điều khiển.
5. Property và target phụ thuộc nhau đến mức khó xác định giá trị nào có ở thời điểm nào.
6. Một lỗi nhỏ trong luồng điều khiển khiến việc hiểu thứ tự thực thi mất nhiều thời gian.

Không phải cứ có một điều kiện là cần cài extension. Với một hoặc hai nhánh đơn giản, target condition thường là lựa chọn dễ đọc nhất.

## 9. Phần mở rộng Ant-Contrib

Ant-Contrib là một tập hợp task và type bổ sung cho Ant. Nó thường được dùng khi build cần các cấu trúc điều khiển như `if/then/else`, vòng lặp `for`, `foreach`, `while`, `switch` hoặc `try/catch`.

Ant-Contrib là phần mở rộng bên ngoài Ant lõi. Muốn dùng, cần cài JAR tương thích và khai báo task bằng `taskdef`. Ví dụ cách nạp antlib:

```xml
<project name="extended-build" default="build" basedir=".">
    <taskdef resource="net/sf/antcontrib/antlib.xml"/>

    <property name="environment" value="dev"/>

    <target name="build">
        <if>
            <equals arg1="${environment}" arg2="production"/>
            <then>
                <echo message="Production build selected"/>
            </then>
            <else>
                <echo message="Non-production build selected"/>
            </else>
        </if>
    </target>
</project>
```

JAR Ant-Contrib phải nằm trên classpath của Ant hoặc được cung cấp theo cách `taskdef` có thể nạp được. Cách cài đặt cụ thể phụ thuộc môi trường và phiên bản Ant/Ant-Contrib; trong CI nên khai báo dependency này rõ ràng thay vì dựa vào thư viện cài thủ công trên một máy.

### 9.1. Dùng if/then/else

Với Ant-Contrib, nhánh có thể được viết ngay trong một target:

```xml
<if>
    <equals arg1="${environment}" arg2="production"/>
    <then>
        <echo message="Run production preparation"/>
        <copy file="config/prod.properties" tofile="build/app.properties"/>
    </then>
    <else>
        <echo message="Run development preparation"/>
        <copy file="config/dev.properties" tofile="build/app.properties"/>
    </else>
</if>
```

Điểm thuận tiện là các task của nhánh được đặt tại chỗ, giúp đọc một quy trình có điều kiện liên tiếp dễ hơn. Điều kiện con có thể dùng các điều kiện của Ant như `equals`, `available`, `and` hoặc `or`.

### 9.2. Lặp qua danh sách bằng for

Task `for` của Ant-Contrib cho phép thực hiện một chuỗi task với từng phần tử trong danh sách:

```xml
<for list="dev,test,production" param="env">
    <sequential>
        <echo message="Preparing environment @{env}"/>
    </sequential>
</for>
```

`param` đặt tên biến vòng lặp, và `@{env}` tham chiếu giá trị hiện tại trong phần `sequential`. Ví dụ này chỉ in tên môi trường, nhưng có thể thay bằng các task chuẩn bị tương ứng.

Không nên nhầm `@{env}` của macro/Ant-Contrib với `${env}` của Ant property. Property Ant có tính bất biến; biến tham số macro được thay thế theo lần gọi hoặc lần lặp.

### 9.3. Dùng foreach để gọi target nhiều lần

`foreach` của Ant-Contrib phù hợp khi mỗi phần tử cần gọi một target riêng. Target được gọi nhận giá trị thông qua property tham số.

```xml
<target name="build-environments">
    <foreach list="dev,test,production"
             param="environment"
             target="build-one-environment"/>
</target>

<target name="build-one-environment">
    <echo message="Building ${environment}"/>
</target>
```

`for` đặt một chuỗi task bên trong vòng lặp; `foreach` gọi một target cho từng phần tử. Chọn loại phù hợp với cách tổ chức build và kiểm tra tài liệu của phiên bản Ant-Contrib đang cài để biết chính xác cách truyền property, kế thừa property và xử lý lỗi.

## 10. Cài đặt và quản lý phần mở rộng có kiểm soát

Khi thêm Ant-Contrib hoặc một thư viện task khác, cần quản lý nó như dependency của build tool:

1. Chọn phiên bản extension tương thích với phiên bản Ant và JDK đang dùng.
2. Lưu hoặc tải JAR từ nguồn đáng tin cậy và khóa phiên bản trong quy trình build.
3. Đưa JAR vào classpath của Ant hoặc khai báo classpath trong `taskdef`.
4. Khai báo `taskdef` rõ ràng trong build file hoặc một file build support dùng chung.
5. Bảo đảm máy cá nhân và CI dùng cùng phiên bản extension.
6. Nếu task không được nhận diện, kiểm tra log nạp task, đường dẫn JAR và tên resource antlib.

Ví dụ `taskdef` có chỉ định classpath tường minh:

```xml
<taskdef resource="net/sf/antcontrib/antlib.xml"
         classpath="tools/ant-contrib.jar"/>
```

Đường dẫn trên là ví dụ tương đối với thư mục chứa `build.xml`. Trong dự án thật, có thể dùng property `tools.dir` để tránh hard-code đường dẫn ở nhiều nơi.

Không nên thêm extension chỉ vì nó có nhiều task tiện lợi. Mỗi extension bổ sung một yêu cầu cài đặt và tương thích cho tất cả môi trường build. Hãy cân nhắc lợi ích đọc hiểu và giảm độ phức tạp trước khi đưa dependency mới vào.

## 11. Khi nào nên dùng script hoặc custom task?

Nếu logic cần xử lý dữ liệu phức tạp, gọi API hoặc áp dụng thuật toán riêng, có thể cân nhắc một trong các hướng sau:

### Script task

Ant có task `<script>` và cơ chế định nghĩa task bằng script trong một số cấu hình. Cách này cho phép viết logic bằng ngôn ngữ script nếu runtime có scripting engine tương thích. Khả năng sử dụng phụ thuộc JDK, engine và phiên bản Ant; không nên giả định mọi máy chạy Ant đều có sẵn cùng một engine.

Script phù hợp với một đoạn tự động hóa nhỏ, nhưng cần giữ script ngắn, kiểm soát dependency và tránh đưa logic build quan trọng vào mã khó kiểm thử hoặc khó tái sử dụng.

### Custom task bằng Java

Khi logic phức tạp và có thể tái sử dụng, viết một custom task Java là lựa chọn có cấu trúc hơn. Task có thể nhận attribute/nested element, kiểm tra đầu vào và phát sinh `BuildException` khi thao tác không thành công.

Custom task cần được biên dịch, đóng gói và nạp vào Ant bằng `taskdef`. Cần quản lý JAR, phiên bản Ant API và dependency của task như một thành phần của build infrastructure.

### Tách logic sang chương trình riêng

Nếu thao tác đã có một CLI chuyên dụng, có thể gọi nó bằng `<exec>`. Ant giữ vai trò điều phối; chương trình bên ngoài thực hiện xử lý dữ liệu. Dùng `failonerror="true"` khi mã thoát khác 0 phải làm build thất bại.

```xml
<exec executable="java" failonerror="true">
    <arg value="-jar"/>
    <arg value="tools/release-checker.jar"/>
    <arg value="dist/app.zip"/>
</exec>
```

Giữ giao diện dòng lệnh ổn định và xử lý exit code rõ ràng để build có thể chạy nhất quán trên máy cá nhân và CI.

## 12. Chọn giữa Ant lõi, Ant-Contrib và công cụ khác

| Nhu cầu | Hướng phù hợp | Lý do |
|---|---|---|
| Build tuyến tính theo thứ tự cố định | Ant lõi với `depends` | Đơn giản và dễ theo dõi |
| Một vài nhánh theo môi trường | `condition` và target `if`/`unless` | Không cần cài thêm thư viện |
| Xác thực đầu vào và dừng khi không hợp lệ | `<available>`, `<condition>`, `<fail>` | Có thể thể hiện rõ quy tắc build |
| Xử lý hàng loạt file | `fileset`, resource collection và task chuẩn | Không cần tự tạo vòng lặp |
| Lặp danh sách hoặc if/else lồng trong target | Ant-Contrib | Bổ sung cấu trúc điều khiển trực tiếp |
| Logic nghiệp vụ riêng, phức tạp và tái sử dụng | Custom task Java hoặc CLI riêng | Có thể kiểm thử và đóng gói logic độc lập |
| Dự án mới cần dependency graph, vòng đời và multi-module hiện đại | Đánh giá Maven hoặc Gradle | Có mô hình build cấp cao hơn và hệ sinh thái tương ứng |

Không có quy tắc rằng mọi build phức tạp đều phải rời Ant. Nhiều dự án cũ vẫn phù hợp với Ant nếu build script được tổ chức tốt. Nhưng nếu phần lớn file chỉ còn là cách mô phỏng một ngôn ngữ lập trình, chi phí bảo trì có thể lớn hơn lợi ích của việc giữ mọi logic trong Ant.

## 13. Cách giữ build script dễ bảo trì

Một số nguyên tắc giúp tránh biến build file thành một chương trình khó hiểu:

1. Dùng target để đặt tên cho các bước nghiệp vụ: `validate`, `compile`, `test`, `package`, `publish`.
2. Dùng `depends` cho thứ tự bắt buộc và giữ dependency graph càng rõ càng tốt.
3. Dùng property và `<condition>` cho các quyết định đơn giản theo cấu hình.
4. Đặt task riêng của từng nhánh bên trong target có điều kiện, tránh đưa side effect vào dependency sẽ luôn chạy.
5. Dùng task xử lý resource collection thay vì lặp thủ công trên từng file.
6. Dùng `macrodef` khi cần đóng gói một chuỗi task lặp lại với vài tham số.
7. Dùng Ant-Contrib khi cấu trúc if/else hoặc vòng lặp làm build rõ hơn đáng kể; ghi rõ dependency và phiên bản extension.
8. Chuyển logic tính toán phức tạp sang custom task hoặc chương trình riêng có thể kiểm thử.
9. Viết thông báo lỗi có ngữ cảnh và để build thất bại khi điều kiện bắt buộc không đạt.
10. Chạy cùng một build trên máy cá nhân và CI để phát hiện extension hoặc runtime bị thiếu.

## 14. Bài tập thực hành

### Bài 1: Rẽ nhánh bằng Ant lõi

Tạo property `environment` mặc định là `dev`. Dùng `<condition>` tạo property `is.production`, rồi tạo hai target `build-production` và `build-development` với `if`/`unless`. Gọi chúng qua target `dispatch` và thử cả hai môi trường.

### Bài 2: Xử lý file theo tập tài nguyên

Tạo mười file `.properties`. Dùng một fileset và task `<copy>` để copy tất cả file phù hợp. Thêm `exclude` cho file local. Xác nhận không cần một target riêng cho từng file.

### Bài 3: Dùng Ant-Contrib if/else

Cài Ant-Contrib tương thích, khai báo `taskdef`, rồi thay hai nhánh target trong bài 1 bằng task `<if>` với `<then>` và `<else>`. So sánh độ rõ ràng của hai cách tổ chức.

### Bài 4: Lặp danh sách bằng for

Tạo danh sách `dev,test,production`, dùng Ant-Contrib `<for>` để in từng môi trường. Sau đó thêm một bước chuẩn bị file cho từng giá trị.

### Bài 5: Chọn đúng công cụ

Viết mô tả một build cần lặp qua hàng trăm module, có nhiều nhánh điều kiện và xử lý lỗi riêng cho từng module. Đề xuất giữ Ant lõi, thêm Ant-Contrib, viết custom task hay chuyển một phần logic sang chương trình riêng. Giải thích chi phí cài đặt, tính dễ đọc và khả năng chạy trên CI.

Sau khi hoàn thành, người học cần biết giới hạn điều khiển luồng của Ant lõi, tự biểu diễn được nhánh đơn giản bằng target condition và nhận ra lúc nào phần mở rộng thực sự giúp build dễ hiểu hơn.

## 15. Nguyên tắc quyết định

Ant lõi mạnh ở việc mô tả dependency, gọi task và xử lý tập tài nguyên. Hãy dùng target, property và condition cho các quyết định đơn giản; dùng task xử lý nhiều file khi công việc có tính đồng nhất. Chỉ thêm Ant-Contrib hoặc custom task khi build thực sự cần vòng lặp, nhánh phức tạp hoặc logic chuyên biệt.

Mục tiêu của phần mở rộng là làm luồng build rõ ràng và dễ vận hành hơn. Nếu extension khiến mọi máy build phải cài thêm nhiều thành phần mà chỉ giải quyết một điều kiện nhỏ, cơ chế sẵn có của Ant thường là lựa chọn hợp lý hơn.
