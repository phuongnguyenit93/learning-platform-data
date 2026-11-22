# Chẩn đoán property chưa được đặt hoặc có giá trị ngoài dự kiến trong Apache Ant

Trong Apache Ant, **property** là các giá trị được đặt tên dùng để cấu hình quá trình build: đường dẫn thư mục, tên ứng dụng, phiên bản, môi trường chạy hoặc lựa chọn đóng gói. Một lỗi property đôi khi biểu hiện rất rõ, ví dụ đường dẫn đầu ra còn chứa `${build.dir}`; đôi khi lại âm thầm làm build dùng nhầm cấu hình vì một giá trị mặc định được đặt trước giá trị mong muốn.

Bài này tập trung vào cách **đọc nhật ký, xác định nguồn gốc giá trị, phân biệt property chưa được đặt với property sai giá trị, và báo lỗi sớm** trong tệp `build.xml` của Ant.

## 1. Property được Ant xử lý như thế nào?

### Khai báo và sử dụng

Một property thường được khai báo bằng `<property>` rồi tham chiếu qua `${tên.property}`:

```xml
<project name="demo" default="show" basedir=".">
    <property name="app.name" value="sample-app"/>
    <property name="build.dir" location="build"/>

    <target name="show">
        <echo message="Application: ${app.name}"/>
        <echo message="Build directory: ${build.dir}"/>
    </target>
</project>
```

Trong ví dụ, `app.name` chứa chuỗi `sample-app`, còn `build.dir` chứa **đường dẫn được chuẩn hóa** từ thư mục `build` tương đối với `basedir` của project. Lệnh `ant show` sẽ in các giá trị thực tế để quan sát.

Ant cũng có thể nhận property từ tệp `.properties`, đối số dòng lệnh `-D`, các property có sẵn của Ant/JVM, biến môi trường được nạp tường minh, hay tác vụ tính toán ra giá trị.

### Ba quy tắc cần nhớ khi chẩn đoán

1. **Tên property phân biệt chữ hoa, chữ thường và ký tự.** `build.dir`, `buildDir` và `BUILD_DIR` là ba tên khác nhau.
2. **Property thông thường có tính chất gán lần đầu rồi giữ nguyên.** Khi property đã được đặt, một khai báo `<property>` sau đó thường không ghi đè được nó. Property người dùng từ `-D` có mức ưu tiên đặc biệt và được bảo vệ khỏi bị các khai báo trong build ghi đè.
3. **Tham chiếu đến property chưa được đặt thường giữ nguyên biểu thức `${...}`** thay vì tự biến thành chuỗi rỗng. Vì thế, nhật ký dạng `Output: ${output.dir}` là một tín hiệu hữu ích.

Ví dụ điển hình của quy tắc thứ hai:

```xml
<property name="build.mode" value="dev"/>
<property name="build.mode" value="prod"/>

<target name="show-mode">
    <echo message="build.mode=${build.mode}"/>
</target>
```

Nếu không có nguồn đặt `build.mode` trước hai khai báo đó, kết quả là `dev`, không phải `prod`. Khi một property sai giá trị, việc tìm **lần gán thành công đầu tiên** quan trọng hơn tìm khai báo cuối cùng.

> Một property **đã tồn tại nhưng rỗng** khác với property **chưa tồn tại**. Ví dụ `<property name="app.name" value=""/>` vẫn tạo property `app.name`; kiểm tra chỉ bằng `unless="app.name"` sẽ không coi nó là thiếu.

## 2. Đọc triệu chứng từ nhật ký build

| Dấu hiệu quan sát được | Khả năng nguyên nhân | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `[echo] Path=${output.dir}` | `output.dir` chưa được định nghĩa hoặc viết sai tên | So khớp tên property; kiểm tra lệnh nạp cấu hình |
| `[echo] build.mode=dev` dù file ghi `prod` | Giá trị `dev` đã được đặt trước; tệp cấu hình không được nạp hoặc không ghi đè được | Xem thứ tự `<property>`, `-D` và nhật ký `-verbose` |
| Đường dẫn trỏ vào thư mục không mong muốn | `basedir` khác dự đoán; nhầm `value` với `location`; giá trị tương đối | In `${basedir}`, đường dẫn đã phân giải và vị trí file build |
| Build chạy target không mong đợi dù property là `false` | Dùng `if`/`unless` theo **sự tồn tại** của property thay vì so sánh giá trị | Kiểm tra điều kiện của target; dùng `<condition>` khi cần kiểm tra boolean |
| Lỗi xuất hiện ở tác vụ `<javac>`, `<copy>` hoặc `<jar>` | Một property đường dẫn sai đã được dùng trước khi có bước kiểm tra | In và xác thực property ngay trước tác vụ phụ thuộc |
| Có property khi chạy thủ công nhưng thiếu trong CI | CI không truyền `-D`, không có biến môi trường hoặc không có file cấu hình | Đối chiếu tham số lệnh, working directory và file có mặt trong môi trường CI |

Hãy tìm **thông báo lỗi đầu tiên có liên quan** thay vì chỉ đọc dòng `BUILD FAILED` cuối cùng. Dòng cuối thường chỉ cho biết Ant đã dừng; vị trí target và giá trị property được in trước đó mới giúp khoanh vùng nguyên nhân.

## 3. Ví dụ tái hiện: property bị thiếu và property sai giá trị

Tạo cấu trúc thư mục:

```text
ant-property-demo/
├── build.xml
└── build.properties
```

### Tệp `build.properties`

```properties
app.name=inventory-service
build.mode=prod
```

### Tệp `build.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="property-demo" default="build" basedir=".">

    <!-- Đọc cấu hình dự án trước khi đặt giá trị mặc định. -->
    <property file="build.properties"/>

    <!-- Chỉ dùng dev khi chưa có nguồn nào đặt build.mode. -->
    <property name="build.mode" value="dev"/>
    <property name="output.dir" location="build/${build.mode}"/>

    <target name="inspect" description="In các property an toàn để chẩn đoán">
        <echo level="info" message="app.name=[${app.name}]"/>
        <echo level="info" message="build.mode=[${build.mode}]"/>
        <echo level="info" message="output.dir=[${output.dir}]"/>
        <echo level="info" message="basedir=[${basedir}]"/>
    </target>

    <target name="validate" depends="inspect"
            description="Xác thực cấu hình trước khi build">
        <fail unless="app.name"
              message="Thiếu app.name: đặt trong build.properties hoặc truyền -Dapp.name=..."/>

        <condition property="app.name.nonempty">
            <not>
                <equals arg1="${app.name}" arg2="" trim="true"/>
            </not>
        </condition>
        <fail unless="app.name.nonempty"
              message="app.name không được rỗng hoặc chỉ có khoảng trắng"/>

        <condition property="build.mode.valid">
            <or>
                <equals arg1="${build.mode}" arg2="dev"/>
                <equals arg1="${build.mode}" arg2="prod"/>
            </or>
        </condition>
        <fail unless="build.mode.valid"
              message="build.mode chỉ được là dev hoặc prod; giá trị hiện tại: ${build.mode}"/>
    </target>

    <target name="build" depends="validate"
            description="Tạo file đánh dấu sau khi kiểm tra cấu hình">
        <mkdir dir="${output.dir}"/>
        <echo file="${output.dir}/build.txt"
              message="${app.name} (${build.mode})"/>
    </target>
</project>
```

Trong ví dụ, `inspect` chỉ in những giá trị không nhạy cảm; `validate` đảm bảo các điều kiện tối thiểu; `build` chỉ tạo đầu ra sau khi validation thành công. Các tên property phục vụ kiểm tra (`app.name.nonempty`, `build.mode.valid`) được đặt riêng để không nhầm với tên cấu hình đầu vào.

### Tình huống A: cấu hình đầy đủ

Chạy từ thư mục `ant-property-demo`:

```bash
ant inspect
ant build
```

Các dòng thông tin có ý nghĩa sẽ giống:

```text
[echo] app.name=[inventory-service]
[echo] build.mode=[prod]
[echo] output.dir=[.../ant-property-demo/build/prod]
```

Dấu `...` đại diện phần đường dẫn tuyệt đối tùy máy, không phải đầu ra nguyên văn của Ant. Sau `ant build`, file `build/prod/build.txt` được tạo.

### Tình huống B: thiếu property bắt buộc

Nếu xóa dòng `app.name=inventory-service` khỏi `build.properties` và không truyền `-Dapp.name`, `ant build` sẽ cho thấy:

```text
[echo] app.name=[${app.name}]
...
BUILD FAILED
... Thiếu app.name: đặt trong build.properties hoặc truyền -Dapp.name=...
```

`<fail unless="app.name">` giúp dừng ngay tại điểm cấu hình đầu vào, thay vì để chuỗi `${app.name}` đi xa hơn tới tác vụ tạo file hoặc đóng gói.

### Tình huống C: giá trị ngoài danh sách hợp lệ

Thay `build.mode=prod` thành `build.mode=production` rồi chạy:

```bash
ant build
```

`inspect` sẽ in `build.mode=[production]`. Target `validate` dừng với thông báo `build.mode chỉ được là dev hoặc prod...` nhờ `<condition>` kết hợp `<equals>`; không tạo thư mục đầu ra theo mode sai.

### Tình huống D: chạy với giá trị từ dòng lệnh

Khi cần kiểm tra liệu cấu hình có bị nguồn khác ghi đè hay không, chạy:

```bash
ant -Dbuild.mode=dev inspect
ant -Dapp.name=demo-app -Dbuild.mode=dev build
```

Những property truyền bằng `-D` được Ant tiếp nhận như **user properties**. Vì vậy, `build.mode=dev` từ dòng lệnh có hiệu lực dù `build.properties` vẫn chứa `build.mode=prod`. Đây cũng là lý do CI và máy phát triển có thể cho kết quả khác nhau dù cùng một `build.xml`.

## 4. Cách truy tìm nguồn đặt property

Một property có thể xuất hiện ở nhiều nơi. Muốn tìm lý do một giá trị thắng giá trị khác, hãy lần theo **thời điểm nạp** và **loại nguồn** của nó.

### 4.1. Xem tham số lệnh Ant trước

Ví dụ:

```bash
ant -Dbuild.mode=prod build
ant -f build.xml -verbose inspect
ant -f build.xml -debug inspect
```

- `-Dname=value` đặt user property trước khi các khai báo build thông thường được thực thi. Trong trường hợp trùng tên, một `<property>` trong XML không ghi đè giá trị này.
- `-verbose` hiển thị thông tin chi tiết hơn, hữu ích để nhận thấy property đã được định nghĩa và một lần cố đặt lại bị bỏ qua.
- `-debug` đưa ra thêm chi tiết cấu hình và thực thi khi `-verbose` chưa đủ. Log debug có thể lớn và không phải dòng nào cũng chỉ rõ nguồn gốc cuối cùng của property.

Không nhất thiết bật `-debug` trong mọi lần build. Nên bắt đầu bằng `inspect` và `-verbose` vì chúng tạo ít thông tin gây nhiễu hơn.

### 4.2. Kiểm tra thứ tự các khai báo trong `build.xml`

Hai đoạn dưới đây **không tương đương**:

```xml
<!-- A: giá trị trong file được ưu tiên; default chỉ điền chỗ thiếu. -->
<property file="build.properties"/>
<property name="build.mode" value="dev"/>
```

```xml
<!-- B: dev đã được đặt, file không thể thay giá trị đó. -->
<property name="build.mode" value="dev"/>
<property file="build.properties"/>
```

Giả sử `build.properties` chứa `build.mode=prod` và không có `-Dbuild.mode`: đoạn A tạo `prod`, còn đoạn B giữ `dev`. Khi khai báo mặc định, nên đặt chúng **sau** nguồn cấu hình muốn ưu tiên.

Một điểm khác: `build.properties` không tự động được Ant nạp chỉ vì file tồn tại. Phải có `<property file="..."/>` hoặc cách nạp tương ứng. Nếu file không nằm ở vị trí được tham chiếu, các property dự kiến sẽ không xuất hiện.

### 4.3. Kiểm tra thời điểm thực thi target

Khai báo một property trong target `init` không bảo đảm target `inspect` nhìn thấy giá trị đó nếu `init` chưa chạy:

```xml
<target name="init">
    <property name="revision" value="r42"/>
</target>

<target name="inspect" depends="init">
    <echo message="revision=${revision}"/>
</target>
```

Ở đây `depends="init"` đảm bảo `revision` được thiết lập trước khi task `<echo>` của `inspect` chạy. Nếu bỏ `depends` rồi gọi riêng `ant inspect`, kết quả có thể còn `${revision}`. Với cấu hình cần dùng ở nhiều target, có thể nạp tại cấp project hoặc trong một target khởi tạo chung mà các target cần cấu hình đều phụ thuộc vào.

### 4.4. Phân biệt đường dẫn tương đối và giá trị văn bản

Hai cách khai báo sau tạo ra ý nghĩa khác nhau:

```xml
<property name="path.as.text" value="build/output"/>
<property name="path.resolved" location="build/output"/>
```

`value` giữ chuỗi, còn `location` xử lý theo ngữ nghĩa đường dẫn và thường tạo ra đường dẫn tuyệt đối dựa trên thư mục gốc project. Khi đường dẫn không như mong đợi, in cả `${basedir}` và property đích. Đặc biệt cẩn thận với `<import>`: tệp được import có thể nằm ở thư mục khác, nhưng các đường dẫn tương đối trong tác vụ thường vẫn được giải quyết theo `basedir` của project đang chạy.

### 4.5. Phân biệt biến môi trường với property Ant

Biến môi trường của hệ điều hành không tự động trở thành property `${env.NAME}`. Muốn dùng cú pháp đó, cần nạp chúng:

```xml
<property environment="env"/>

<target name="inspect-env">
    <echo message="JAVA_HOME from environment: ${env.JAVA_HOME}"/>
</target>
```

Tên môi trường phụ thuộc hệ điều hành và môi trường chạy. Nếu `JAVA_HOME` không tồn tại, `${env.JAVA_HOME}` có thể vẫn là biểu thức chưa được thay thế. Đừng nhầm `${env.JAVA_HOME}` với `${java.home}`: cái thứ hai thường là Java system property chỉ thư mục runtime của JVM đang chạy Ant, không nhất thiết là biến `JAVA_HOME` người dùng khai báo.

Nếu nghi ngờ lỗi trên CI, so sánh các điều kiện liên quan: **thư mục làm việc, file cấu hình có mặt, biến môi trường thực tế, tham số `-D`, và những tệp build được import**.

## 5. Dùng tác vụ Ant để kiểm tra và báo lỗi rõ ràng

### Kiểm tra property có được đặt hay chưa

Nếu chỉ yêu cầu property tồn tại:

```xml
<target name="check-required-property">
    <fail unless="release.version"
          message="Thiếu release.version; truyền -Drelease.version=..."/>
</target>
```

`unless` ở đây kiểm tra **sự tồn tại của property**, không kiểm tra chuỗi có rỗng hay không, cũng không giải thích `false` như một giá trị boolean.

Có thể dùng `<isset>` để tạo kết quả điều kiện phục vụ bước sau:

```xml
<condition property="release.version.present">
    <isset property="release.version"/>
</condition>
```

`release.version.present` chỉ được đặt khi điều kiện đúng, trong bối cảnh chưa có property cùng tên từ trước. Hãy đặt tên các property điều kiện rõ ràng và tránh khai báo sẵn chúng với một giá trị gây hiểu nhầm.

### Kiểm tra giá trị không rỗng hoặc không nằm ngoài phạm vi

Với một property bắt buộc, nên kiểm tra **tồn tại trước**, sau đó kiểm tra nội dung:

```xml
<target name="validate-release">
    <fail unless="release.version" message="Thiếu release.version"/>

    <condition property="release.version.nonempty">
        <not>
            <equals arg1="${release.version}" arg2="" trim="true"/>
        </not>
    </condition>
    <fail unless="release.version.nonempty"
          message="release.version không được để trống"/>
</target>
```

Khi giá trị chỉ được phép nằm trong một tập hữu hạn, dùng `<or>` và `<equals>` giống `build.mode.valid` ở ví dụ chính. Cách này cho thông báo lỗi dễ hiểu hơn so với việc để một tác vụ phía sau thất bại vì cấu hình không hợp lệ.

### Kiểm tra file cấu hình hoặc tài nguyên cần thiết

Một property có giá trị đường dẫn vẫn có thể trỏ đến file không tồn tại. Có thể xác thực sự tồn tại bằng `<available>`:

```xml
<target name="check-config-file">
    <available file="config/application.properties"
               property="config.file.exists"/>
    <fail unless="config.file.exists"
          message="Không tìm thấy config/application.properties"/>
</target>
```

Điều này phân biệt hai lỗi khác nhau: **property chưa được thiết lập** và **property đã được thiết lập nhưng trỏ đến tài nguyên sai**. Khi kiểm tra lặp lại trong cùng phiên Ant, nên dùng property điều kiện có tên riêng cho từng điều kiện thay vì giả định có thể đặt lại nó nhiều lần.

## 6. Nhật ký nào hữu ích, nhật ký nào dễ gây hiểu nhầm?

Ant cung cấp nhiều mức log. `<echo level="info">` phù hợp để in thông tin cấu hình tối thiểu trong output thông thường; `-verbose` và `-debug` hỗ trợ phân tích khi nghi ngờ sự kiện gán property hoặc cách Ant giải quyết task.

Đối với một build thất bại do property, một chuỗi nhật ký có ích thường cho biết:

```text
inspect:
     [echo] app.name=[inventory-service]
     [echo] build.mode=[production]
     [echo] output.dir=[.../build/production]
validate:
BUILD FAILED
... build.mode chỉ được là dev hoặc prod ...
```

Nhờ vậy, người đọc biết **giá trị thực tế**, **target phát hiện lỗi** và **quy tắc bị vi phạm**. Chỉ ghi `BUILD FAILED` hoặc `Invalid configuration` sẽ khó truy tìm hơn.

Ant có tác vụ `<echoproperties>` để liệt kê property; tính năng này có ích trong môi trường thử nghiệm kiểm soát được. Tuy nhiên, việc in **toàn bộ** property, đặc biệt khi bật `-debug`, có thể làm lộ token, mật khẩu hoặc thông tin nội bộ trong log CI. Hãy ưu tiên in một số tên property **đã chọn và không nhạy cảm**; không đưa bí mật vào ví dụ log hoặc gửi nguyên log debug ra nơi công khai.

Lệnh `ant -diagnostics` chủ yếu phục vụ thu thập thông tin môi trường Ant/Java và các thành phần hỗ trợ. Nó hữu ích khi nghi lỗi môi trường hoặc phiên bản, nhưng **không thay thế** bước kiểm tra nguồn đặt một property cụ thể trong `build.xml`.

## 7. Các bẫy thường gặp khi xử lý property

### Dùng property `false` để tắt target

Ví dụ:

```xml
<property name="skip.tests" value="false"/>

<target name="tests" unless="skip.tests">
    <echo message="Run tests"/>
</target>
```

`tests` bị bỏ qua vì `skip.tests` **đã được đặt**, dù chuỗi của nó là `false`. `if` và `unless` truyền thống trên target kiểm tra sự tồn tại của property, không diễn giải chuỗi boolean. Nếu muốn dùng `true`/`false`, hãy tạo một property điều kiện đúng/sai bằng `<condition>` hoặc lựa chọn cơ chế điều kiện phù hợp phiên bản Ant.

### Tưởng file được import đặt lại mọi property

Nếu project chính đặt `build.mode=dev` trước rồi import file chung cố đặt `build.mode=prod`, giá trị đầu vẫn được giữ. `import` dùng để đưa định nghĩa build chung vào, không phải cơ chế xóa hoặc ghi đè các property đã tồn tại. Hãy xác định rõ nguồn nào cần được quyền cung cấp giá trị trước khi sắp xếp thứ tự khai báo.

### Nhầm property của target con với project cha

Khi dùng `<ant>` hoặc `<antcall>`, Ant có thể thực thi target trong **ngữ cảnh project mới** với các quy tắc chuyển property riêng. Một property được tạo trong lần gọi con không tự động trở về thay đổi giá trị ở project gọi. Nếu cần chuyển dữ liệu giữa các bước, hãy thiết kế đầu vào/đầu ra tường minh, thay vì kỳ vọng property ở project cha sẽ bị cập nhật sau lời gọi.

### Đọc log ở sai thư mục làm việc

Hai lệnh chạy từ hai thư mục khác nhau có thể đọc những đường dẫn tương đối khác nhau nếu cấu hình `basedir`, tệp build và đầu vào không tương ứng. Trong script CI, nên truyền rõ file build cần chạy (`ant -f path/to/build.xml ...`) và in đường dẫn đã phân giải khi cần đối chiếu. Chỉ dựa vào chuỗi `build` hoặc `config.properties` mà không biết đường dẫn gốc dễ dẫn đến kết luận sai.

### Cố sửa một property bằng một khai báo thứ hai

Vì property thường không thay đổi sau lần gán đầu, viết tiếp `<property name="build.mode" value="dev"/>` không giải quyết được lỗi `build.mode=production`. Cần sửa **nguồn ban đầu**, **thứ tự nạp** hoặc **đối số `-D`**, rồi chạy lại build để tạo một project Ant mới với tập property đúng.

## 8. Quy trình chẩn đoán thực tế

Khi gặp một lỗi cấu hình chưa rõ nguồn gốc, có thể đi theo thứ tự sau:

1. **Ghi lại dấu hiệu:** target bị lỗi, property liên quan, giá trị thực tế (`${...}` còn nguyên, rỗng hay khác mong đợi) và lệnh Ant đã gọi.
2. **In riêng property nghi vấn:** thêm `inspect` bằng `<echo level="info">` ở vị trí trước tác vụ thất bại; với đường dẫn, in thêm `${basedir}`.
3. **Truy nguồn theo thứ tự:** xem `-D`, việc nạp `.properties`, các khai báo ở cấp project, các file import, và các target khởi tạo có được thực thi trước hay không.
4. **Tăng mức log khi cần:** chạy lại với `-verbose`, sau đó `-debug` nếu vẫn chưa xác định được lần đặt đầu tiên hoặc nguyên nhân nạp file thất bại.
5. **Kiểm tra giả thuyết bằng một thay đổi có kiểm soát:** sửa tên property, vị trí nạp file, tham số CLI hoặc giá trị cấu hình cần thiết; chạy `inspect` để quan sát lại.
6. **Đưa lỗi về gần nguồn:** thêm `<fail>`, `<condition>` hoặc `<available>` để lần build tiếp theo dừng với thông báo cụ thể trước khi tạo artifact sai.

Giả sử CI đóng gói vào `build/dev` dù `build.properties` ghi `prod`: hãy quan sát `build.mode`, kiểm tra job có truyền `-Dbuild.mode=dev` không, sau đó kiểm tra xem mặc định `dev` có được khai báo trước khi nạp file hay không. Hai nguyên nhân này dẫn đến cùng triệu chứng nhưng cần sửa ở hai vị trí khác nhau.

Kỹ năng chẩn đoán property trong Ant dựa trên ba câu hỏi xuyên suốt: **property có được đặt không, nó được đặt từ đâu và khi nào, và giá trị hiện tại có hợp lệ đối với bước build sắp chạy không?** Trả lời theo thứ tự đó giúp biến những lỗi `BUILD FAILED` mơ hồ thành thông báo cấu hình cụ thể và dễ sửa.
