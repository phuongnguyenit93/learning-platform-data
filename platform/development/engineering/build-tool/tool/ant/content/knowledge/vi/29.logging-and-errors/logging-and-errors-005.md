# Chẩn đoán target không tồn tại và phụ thuộc vòng trong Apache Ant

Trong Apache Ant, một **target** là đơn vị công việc được khai báo bằng thẻ `<target>` trong `build.xml`. Một target có thể chạy các task như `<mkdir>`, `<javac>`, `<copy>`, `<jar>` hoặc `<echo>`; đồng thời có thể yêu cầu target khác chạy trước thông qua thuộc tính `depends`. Khi Ant báo **target không tồn tại** hoặc **phụ thuộc vòng**, vấn đề thường nằm ở cách Ant đọc tên target và quan hệ giữa các target, chưa phải ở mã Java cần biên dịch.

Bài học này hướng dẫn đọc log, truy ra vị trí khai báo gây lỗi, dựng lại quan hệ phụ thuộc và sửa cấu trúc build sao cho có thể chạy lại một cách có kiểm soát.

## 1. Nắm mô hình thực thi target trước khi đọc lỗi

Một project Ant có thể khai báo target mặc định và các target phụ thuộc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample" default="package" basedir=".">
    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Đang biên dịch"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Đang đóng gói"/>
    </target>
</project>
```

Chạy:

```bash
ant -f build.xml package
```

Ant xác định thứ tự `init` → `compile` → `package`. Nếu chỉ chạy `ant -f build.xml`, Ant sử dụng `default="package"` trong `<project>`. Thuộc tính `depends` nhận danh sách tên target phân cách bởi dấu phẩy, chẳng hạn `depends="init,compile"`.

Có hai quy tắc quan trọng:

- **Tên target phải khớp chính xác.** `compile`, `Compile` và `compiles` là những tên khác nhau. Tên trong lệnh, `default`, `depends` và thuộc tính `target` của `<antcall>` đều cần được kiểm tra.
- **Phụ thuộc phải tạo được thứ tự chạy hợp lệ.** Nếu A yêu cầu B, B yêu cầu C nhưng C lại yêu cầu A, Ant không thể sắp xếp các target thành một thứ tự tuyến tính.

Trong quan hệ phụ thuộc, `depends="init"` nghĩa là Ant cần hoàn thành target `init` trước khi xử lý target đang khai báo. Điều này không có nghĩa target `init` phải nằm trước target kia trong file XML: Ant tính thứ tự từ quan hệ `depends`, không từ thứ tự xuất hiện của các thẻ.

## 2. Nhận diện hai nhóm lỗi trong log

Các câu thông báo có thể khác đôi chút giữa phiên bản Ant hoặc môi trường tích hợp, nhưng ý nghĩa cốt lõi thường như sau:

| Dấu hiệu trong log | Ý nghĩa | Cần kiểm tra trước |
| --- | --- | --- |
| `Target "release" does not exist in the project "sample".` | Có tham chiếu đến `release` nhưng Ant không có target tương ứng trong project đã nạp | Tên target, file build đang chạy, `default`, `depends`, `<antcall>` |
| `Circular dependency: a <- b <- c <- a` | Chuỗi phụ thuộc quay lại target đã có trong đường đi | Toàn bộ quan hệ `depends` của các target xuất hiện trong chuỗi |
| `BUILD FAILED` | Kết luận chung của Ant khi build thất bại | Dòng lỗi cụ thể phía trên, không chẩn đoán chỉ dựa vào dòng này |

Một log điển hình có thể có phần đầu và cuối tương tự:

```text
Buildfile: C:\work\demo\build.xml

BUILD FAILED
Target "release" does not exist in the project "sample".
```

Dòng `Buildfile` đặc biệt hữu ích: nó cho biết Ant đang đọc file nào. Trong workspace có nhiều `build.xml`, sửa đúng nội dung nhưng nhầm file được chạy sẽ khiến lỗi tiếp tục xuất hiện.

Để quan sát rõ hơn, dùng các lệnh sau tại thư mục chứa project:

```bash
ant -f build.xml -projecthelp
ant -f build.xml -verbose package
ant -f build.xml -debug package
```

`-projecthelp` (viết tắt `-p`) trình bày thông tin target; thông thường các target có `description` sẽ nổi bật, nên **không coi danh sách rút gọn này là bằng chứng rằng mọi target khác đều không tồn tại**. `-verbose` cho thêm ngữ cảnh về file và bước thực thi. `-debug` chi tiết hơn nhưng có thể rất dài; chỉ dùng khi log thường chưa đủ xác định nguyên nhân.

Ví dụ lưu log để tra cứu về sau:

```bash
ant -f build.xml -verbose package > ant-build.log 2>&1
```

Nếu build dùng biến môi trường, đường dẫn hay thông tin xác thực, cân nhắc ẩn dữ liệu nhạy cảm trước khi chia sẻ log, nhất là log chế độ `-debug`.

## 3. Lỗi target không tồn tại: nguyên nhân và cách lần theo

### 3.1. Gõ sai tên khi gọi Ant

Xét file:

```xml
<project name="shop" default="release">
    <target name="compile"/>
    <target name="release" depends="compile"/>
</project>
```

Lệnh sau sai chính tả:

```bash
ant -f build.xml relase
```

Ant tìm target tên `relase` và không thấy. Cách sửa là gọi đúng:

```bash
ant -f build.xml release
```

Kiểm tra cả chữ hoa/chữ thường, dấu gạch nối và khoảng trắng trong giá trị tên. Không nên tạo thêm một target tên sai chỉ để che lỗi đánh máy, trừ khi thực sự muốn cung cấp alias tương thích có chủ đích.

### 3.2. Giá trị `default` trỏ đến target đã đổi tên hoặc bị xóa

```xml
<project name="shop" default="deploy">
    <target name="package">
        <echo message="Packaging"/>
    </target>
</project>
```

Ở ví dụ này, chỉ cần chạy `ant` cũng gây lỗi vì Ant cố chạy `deploy`, trong khi file chỉ khai báo `package`. Nếu bước cuối của build thực sự là đóng gói, hãy sửa thành `default="package"`. Nếu cần triển khai, hãy khai báo `deploy` thật sự và xác định quan hệ của nó với `package`.

Đặc biệt lưu ý những dự án vừa đổi tên target từ `dist` thành `package` hoặc từ `build` thành `assemble`: phải cập nhật cả cấu hình mặc định và lệnh trong IDE/CI.

### 3.3. `depends` trỏ đến target không được định nghĩa

Đây là lỗi dễ bị nhầm vì target được gọi bằng lệnh có thể hoàn toàn hợp lệ:

```xml
<project name="shop" default="release">
    <target name="compile"/>
    <target name="release" depends="comiple">
        <echo message="Releasing"/>
    </target>
</project>
```

Người dùng gọi `release`, nhưng vấn đề nằm ở `depends="comiple"`. Ant phải giải quyết các phụ thuộc của `release` trước khi chạy nội dung target này; target `comiple` không tồn tại, còn target đúng là `compile`.

Sửa đúng vị trí:

```xml
<target name="release" depends="compile">
    <echo message="Releasing"/>
</target>
```

Khi log đề cập một tên lạ, hãy tìm tên đó trong **tất cả nơi tham chiếu**: `default`, `depends`, lệnh chạy, `<antcall target="...">`, và các lệnh gọi build con. Chỉ nhìn danh sách tên `<target>` thường chưa đủ để xác định dòng gây ra lỗi.

### 3.4. Chạy nhầm file build hoặc nhầm project con

Một repository có thể có cấu trúc:

```text
repository/
├── build.xml
├── core/
│   └── build.xml
└── web/
    └── build.xml
```

Target `publish` có thể chỉ được định nghĩa trong `web/build.xml`. Nếu chạy `ant -f build.xml publish` tại gốc repository, Ant không tự tìm target của `web/build.xml`.

Hãy chỉ rõ file tương ứng:

```bash
ant -f web/build.xml publish
```

Đường dẫn trên giả định đang đứng tại thư mục gốc `repository`. Kiểm tra dòng `Buildfile:` trong log để xác nhận file đang nạp. Trong IDE hoặc CI, kiểm tra cả *working directory* và cấu hình `-f`/`-buildfile`; thay đổi nơi chạy lệnh có thể làm một đường dẫn tương đối trỏ đến file khác.

### 3.5. Nhầm tên target được nhập từ file khác

Ant có thể tổ chức cấu hình thành nhiều file qua `<import>` hoặc `<include>`. Tùy cơ chế và cách đặt tên, target được truy cập bằng tên đơn hoặc tên có tiền tố (ví dụ `common.init`). Nếu tham chiếu tên không khớp với các target thực tế đã được nạp, Ant báo target không tồn tại.

Khi gặp tình huống này:

1. Tìm `import`/`include` trong file build đầu vào và xác định những file nào được nạp.
2. Đọc các khai báo `<project name="...">`, `<target name="...">` và tên có tiền tố được dùng trong lệnh hoặc `depends`.
3. Kiểm tra các thay đổi tên file, tên project và prefix; sau đó gọi lại bằng đúng tên đích.

Không mặc định rằng một target có trong *một file bất kỳ* của repository sẽ tự động có mặt trong project Ant hiện tại. Các target chỉ dùng được khi chúng thuộc cấu hình đang thực thi hoặc được gọi qua cơ chế build con phù hợp.

### 3.6. `<antcall>` gọi sai target hoặc tên target động

```xml
<project name="shop" default="run">
    <property name="phase" value="verify"/>

    <target name="run">
        <antcall target="${phase}"/>
    </target>

    <target name="test"/>
</project>
```

Trong ví dụ này, `${phase}` được thay bằng `verify`, nhưng chỉ có target `test`. Cần sửa cấu hình `phase` thành `test` hoặc định nghĩa target `verify` với công việc đúng ý nghĩa. Khi `<antcall target="${...}">` xuất hiện, hãy kiểm tra **giá trị thuộc tính sau khi thay property**, không chỉ chữ được viết trong XML. Property có thể đến từ `-Dphase=...`, file `.properties` hoặc cấu hình môi trường.

## 4. Quy trình chẩn đoán target không tồn tại

Có thể xử lý theo một chuỗi ngắn, mỗi bước xác nhận một giả thuyết:

1. **Ghi lại chính xác tên target trong thông báo lỗi.** Không tự sửa tên đó trong đầu vì một chữ khác biệt cũng đủ gây lỗi.
2. **Xác định file build thực sự được nạp.** Kiểm tra `Buildfile:` và chạy lại với `-f` chỉ rõ đường dẫn.
3. **Xác định nơi tên được yêu cầu.** Kiểm tra đối số lệnh; nếu không có, kiểm tra `default`; sau đó tìm trong `depends`, `<antcall>` và build con.
4. **Đối chiếu các khai báo target.** Kiểm tra chính tả, chữ hoa/thường, scope của file đã import/include và giá trị property khi có tên động.
5. **Sửa một nguyên nhân cụ thể rồi gọi lại đúng target.** Dùng `-verbose` nếu cần nhìn bước nào vẫn tham chiếu tên cũ.

Ví dụ với một lỗi sau khi refactor:

```text
Trước: <target name="compile-java">
Sau:   <target name="compile">
```

Nếu `test` vẫn có `depends="compile-java"`, chỉ đổi tên target khai báo sẽ chưa đủ. Cần sửa các lời gọi và quan hệ liên quan. Tránh chữa lỗi bằng cách thêm nhiều target rỗng vì chúng làm build có vẻ thành công trong khi bỏ qua công việc bắt buộc.

## 5. Lỗi phụ thuộc vòng: Ant không thể chọn thứ tự chạy

Một chu trình phụ thuộc hình thành khi theo các cạnh `depends` rồi quay lại đúng target ban đầu. Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="cycle-demo" default="verify">
    <target name="prepare" depends="verify">
        <echo message="Prepare"/>
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile"/>
    </target>

    <target name="verify" depends="compile">
        <echo message="Verify"/>
    </target>
</project>
```

Phân tích đúng theo câu “A phụ thuộc B”:

```text
verify  --depends on--> compile
compile --depends on--> prepare
prepare --depends on--> verify
          ^                    |
          +------ vòng --------+
```

Khi chạy `ant -f build.xml verify`, Ant không có target hợp lệ để hoàn tất trước toàn bộ các target còn lại. Log thường chứa `Circular dependency:` cùng đường đi qua các target, chẳng hạn:

```text
BUILD FAILED
Circular dependency: verify <- prepare <- compile <- verify
```

Thứ tự tên và cách hiển thị mũi tên có thể khác; thông tin cần giữ lại là **nhóm target tạo thành vòng**. Với phụ thuộc tĩnh khai báo bằng `depends`, Ant kiểm tra thứ tự thực thi trước khi chạy các task của chuỗi đó, nên việc chỉnh sửa source Java hay tăng bộ nhớ JVM không giải quyết được lỗi.

### 5.1. Sửa đúng quan hệ thay vì xóa bừa một `depends`

Ở ví dụ trên, `prepare` được dùng để chuẩn bị thư mục hay dữ liệu, vì vậy nó không hợp lý khi phải chờ `verify`. Nếu quy trình mong muốn là chuẩn bị → biên dịch → kiểm tra, có thể sửa thành:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="cycle-demo" default="verify">
    <target name="prepare">
        <echo message="Prepare"/>
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile"/>
    </target>

    <target name="verify" depends="compile">
        <echo message="Verify"/>
    </target>
</project>
```

Kết quả dự kiến khi chạy `ant -f build.xml verify`:

```text
prepare:
     [echo] Prepare

compile:
     [echo] Compile

verify:
     [echo] Verify

BUILD SUCCESSFUL
```

Mối quan hệ mới có một hướng rõ ràng: `verify → compile → prepare` khi đọc theo chiều “phụ thuộc vào”; thứ tự thực thi ngược lại là `prepare → compile → verify`. Một target chỉ nên phụ thuộc vào công đoạn phải hoàn thành **trước nó**.

### 5.2. Vòng phụ thuộc gián tiếp thường khó thấy hơn

Trong build thực tế, vòng có thể đi qua nhiều target hoặc file khác nhau:

```xml
<target name="all" depends="package"/>
<target name="package" depends="test"/>
<target name="test" depends="compile"/>
<target name="compile" depends="init"/>
<target name="init" depends="all"/>
```

Nếu chỉ kiểm tra `package` và `test`, sẽ không thấy vòng. Phải truy theo `depends` qua `compile`, `init`, rồi quay lại `all`. Cách làm thủ công hiệu quả là lập bảng:

| Target | `depends` trực tiếp | Vai trò mong muốn |
| --- | --- | --- |
| `all` | `package` | Điểm vào tổng hợp |
| `package` | `test` | Đóng gói sau kiểm tra |
| `test` | `compile` | Kiểm tra sau biên dịch |
| `compile` | `init` | Biên dịch sau chuẩn bị |
| `init` | `all` | Chuẩn bị nhưng đang gọi ngược điểm vào |

Quan hệ `init → all` là điểm bất thường. Target khởi tạo thường không cần phụ thuộc vào target tổng hợp; xóa quan hệ đó sau khi đã xác nhận công việc bên trong `init` không cần đầu ra của `all`.

Đối với project nhiều file, có thể vẽ sơ đồ theo tên target đầy đủ (kể cả prefix của target từ file include/import). Mỗi cạnh biểu thị **target đang xét yêu cầu target khác chạy trước**. Nếu có đường quay về nút cũ, cần thiết kế lại quan hệ.

### 5.3. Đừng nhầm điều kiện `if`/`unless` với việc loại bỏ phụ thuộc

Ví dụ:

```xml
<project name="conditional-cycle" default="a">
    <target name="a" depends="b" if="run.a"/>
    <target name="b" depends="a"/>
</project>
```

Ngay cả khi property `run.a` chưa được đặt, quan hệ `a ↔ b` vẫn được khai báo trong `depends`. Trong Ant, điều kiện `if`/`unless` của target được xét đối với việc thực thi phần thân target; các target phụ thuộc vẫn được xử lý. Vì vậy thêm `if` hay `unless` không phải cách hợp lệ để phá chu trình tĩnh. Cần sửa quan hệ phụ thuộc hoặc tách công việc thành target khác.

### 5.4. Tách công đoạn nền tảng khỏi target tổng hợp

Một nguyên nhân kiến trúc phổ biến là target mức thấp phụ thuộc ngược lại target mức cao. Cấu trúc dễ duy trì hơn thường là:

```text
init
  ↓
compile
  ↓
test
  ↓
package
  ↓
release
```

Ở sơ đồ này, mũi tên chỉ **thứ tự công việc**, không phải chiều viết của `depends`. Một cấu hình tương ứng:

```xml
<project name="pipeline" default="release">
    <target name="init"/>
    <target name="compile" depends="init"/>
    <target name="test" depends="compile"/>
    <target name="package" depends="test"/>
    <target name="release" depends="package"/>
</project>
```

Nếu một target tổng hợp như `all` hoặc `release` cần mọi bước, hãy để nó phụ thuộc vào các bước tiền nhiệm. Tránh để các bước nền tảng như `init` hoặc `compile` phụ thuộc vào chính target tổng hợp đó.

## 6. Phân biệt chu trình `depends` với gọi lặp bằng `<antcall>`

Hai kiểu gọi target có cơ chế khác nhau:

```xml
<target name="build" depends="compile"/>
```

`depends` tạo cạnh trong đồ thị phụ thuộc của project. Ant có thể phát hiện chu trình trong đồ thị này.

```xml
<target name="first">
    <antcall target="second"/>
</target>

<target name="second">
    <antcall target="first"/>
</target>
```

`<antcall>` gọi target thông qua một lời gọi Ant mới. Hai target gọi lẫn nhau theo cách này có thể gây đệ quy thực thi, lặp việc hoặc lỗi tràn ngăn xếp, thay vì báo chính xác lỗi `Circular dependency` của `depends`. Vì vậy không nên thay một cạnh `depends` gây vòng bằng `<antcall>` chỉ để tránh thông báo lỗi: hành vi thực thi có thể còn khó kiểm soát hơn.

Khi log không xuất hiện `Circular dependency` nhưng liên tục lặp các tên target hoặc các lần khởi động build con, hãy kiểm tra `<antcall>`, `<ant>` và `<subant>` theo đường đi thực tế. Những lời gọi giữa các project/file build riêng không nhất thiết nằm trong cùng một đồ thị phụ thuộc tĩnh.

## 7. Ví dụ xử lý một sự cố có cả hai loại lỗi

Giả sử nhóm phát triển đổi tên target `unit-test` thành `test`, rồi chỉnh thêm thứ tự đóng gói:

```xml
<project name="demo" default="package">
    <target name="init" depends="package"/>
    <target name="compile" depends="init"/>
    <target name="test" depends="compile"/>
    <target name="package" depends="unit-test"/>
</project>
```

**Lần chạy đầu**, Ant có thể báo không tìm thấy `unit-test`, vì `package` vẫn tham chiếu tên cũ. Sửa `depends="unit-test"` thành `depends="test"` sẽ xử lý lỗi tên, nhưng chưa giải quyết được toàn bộ cấu trúc.

**Lần chạy sau**, chuỗi phụ thuộc trở thành `package → test → compile → init → package`: một chu trình. Phải bỏ quan hệ ngược `init depends="package"` để target `init` đứng độc lập. Cấu hình cuối cùng:

```xml
<project name="demo" default="package">
    <target name="init"/>
    <target name="compile" depends="init"/>
    <target name="test" depends="compile"/>
    <target name="package" depends="test"/>
</project>
```

Trường hợp này cho thấy một log mới sau khi sửa lỗi trước không nhất thiết có nghĩa đã sửa sai: các lỗi cấu hình có thể che lấp nhau. Mỗi lần cần đọc thông báo mới, xác định nguyên nhân mới rồi chỉnh chính xác quan hệ tương ứng.

## 8. Khi build vẫn thất bại sau khi sửa target

Sau khi không còn lỗi tên target hoặc phụ thuộc vòng, Ant có thể bắt đầu thực hiện các task thực tế và báo lỗi khác, chẳng hạn classpath thiếu thư viện, Java biên dịch lỗi, không tìm thấy thư mục nguồn, hoặc quyền ghi file không đủ. Đây là bước chẩn đoán mới.

Nên phân biệt ba giai đoạn:

| Giai đoạn | Dấu hiệu | Hướng giải quyết |
| --- | --- | --- |
| Xác định target | `Target ... does not exist` | Kiểm tra tên tham chiếu và project được nạp |
| Sắp thứ tự phụ thuộc | `Circular dependency` | Tìm và loại bỏ chu trình trong đồ thị `depends` |
| Chạy task trong target | Thông báo lỗi từ `javac`, `copy`, `jar`, `exec`... | Dựa vào task thất bại và thông tin môi trường, không tiếp tục thay tên target tùy ý |

Một cách xác nhận cấu trúc đã hợp lý là chạy target nhỏ trước, rồi mở rộng lên target cao hơn:

```bash
ant -f build.xml init
ant -f build.xml compile
ant -f build.xml test
ant -f build.xml package
```

Các lệnh này minh họa phương pháp khoanh vùng; dùng các tên có thật trong project của bạn. Trong một lần gọi Ant, phụ thuộc của target được xử lý theo thứ tự cần thiết. Chạy từng lệnh tách biệt có thể thực thi lại các công đoạn, vì vậy tránh áp dụng nguyên xi nếu target gây tác động ngoài như triển khai hoặc xóa dữ liệu.

## 9. Thói quen giúp phòng ngừa lỗi

- Đặt tên target nhất quán, dễ hiểu (`init`, `compile`, `test`, `package`, `release`), và cập nhật tất cả tham chiếu khi đổi tên.
- Chọn `default` là một target tồn tại thật, có vai trò rõ ràng; mô tả các target sử dụng thường xuyên bằng thuộc tính `description` để hỗ trợ `ant -p`.
- Giữ quan hệ phụ thuộc hướng từ công đoạn sau về công đoạn trước. Target tổng hợp gọi những bước thành phần, không để bước nền tảng phụ thuộc ngược vào target tổng hợp.
- Với build nhiều module, dùng `-f` và xác nhận `Buildfile:` khi đọc log; rà soát tên có tiền tố sau khi thay đổi `import` hoặc `include`.
- Khi xuất hiện `Circular dependency`, ghi lại chuỗi target trong log, liệt kê `depends` của từng target và xác định cạnh nào trái với quy trình nghiệp vụ trước khi sửa.
- Dùng `<antcall>` khi thật sự cần lời gọi target riêng, không dùng để che chu trình của `depends`.

**Điểm mấu chốt khi chẩn đoán:** `Target ... does not exist` là lỗi **tham chiếu đến tên không được định nghĩa trong project đang chạy**; `Circular dependency` là lỗi **cấu trúc quan hệ giữa những target đã được định nghĩa**. Xác định đúng loại từ log rồi sửa nguồn gốc trong `build.xml` sẽ giúp tránh các bản vá tạm khiến quy trình build khó hiểu về sau.
