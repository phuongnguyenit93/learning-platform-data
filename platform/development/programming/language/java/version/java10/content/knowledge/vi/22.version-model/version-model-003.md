# Cấu trúc chuỗi phiên bản của JDK: FEATURE, INTERIM, UPDATE, PATCH và metadata

> **Java 10 — Mô hình phiên bản.** Từ Java 10, **JEP 322 — Time-Based Release Versioning** đặt lại ý nghĩa bốn thành phần chính của số phiên bản Java SE/JDK thành `FEATURE.INTERIM.UPDATE.PATCH` và giữ khuôn dạng chuỗi có thể thêm thông tin **pre-release**, **build** và **optional**. Cơ chế này vẫn được dùng trên JDK hiện đại. Bài hướng dẫn đọc, phân tích, so sánh và kiểm tra phiên bản bằng `Runtime.Version`, không dùng những quy ước phiên bản Java đã lỗi thời.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **số phiên bản** (`$VNUM`) với **chuỗi phiên bản đầy đủ** (`$VSTR`).
2. Giải thích bốn thành phần `FEATURE`, `INTERIM`, `UPDATE` và `PATCH` theo JEP 322; hiểu vai trò của các thành phần số thứ năm trở đi nếu nhà phân phối sử dụng.
3. Đọc đúng những ví dụ như `21`, `21.0.2`, `21.0.2.1`, `21-ea+28`, `21.0.2+13-LTS` và `21+-LTS`.
4. Giải thích tại sao thành phần 0 ở giữa có thể xuất hiện, nhưng **số phiên bản không được có thành phần 0 cuối cùng**; không dùng các số có leading zero.
5. Dùng `Runtime.Version.parse` để xác thực chuỗi phiên bản, và `feature()`, `interim()`, `update()`, `patch()`, `pre()`, `build()`, `optional()`, `version()` để đọc từng phần.
6. So sánh đúng bằng `compareTo`, `compareToIgnoreOptional` và `equalsIgnoreOptional`, không so sánh toàn bộ chuỗi bằng thứ tự từ điển.
7. Lấy phiên bản JRE **đang chạy** bằng `Runtime.version()`, phân biệt với bản `javac`, cấu hình build, thông tin vendor, ngày phát hành và chuỗi banner dòng lệnh.
8. Thiết kế kiểm tra mức Java tối thiểu, chính sách chấp nhận early-access và yêu cầu bản vá mà không suy diễn rằng chỉ có số FEATURE cao là đã đủ an toàn.
9. Biên dịch và chạy chương trình Java đầy đủ với **29 dòng stdout xác định** trên JDK 17+.

## 2. Bối cảnh Java 10: điều gì đổi và điều gì không đổi?

Java đã có `Runtime.Version` và phương thức `Runtime.version()` từ **Java 9**. **JEP 322** của Java 10 sửa mô hình số phiên bản để phù hợp với chu kỳ phát hành theo thời gian, đồng thời đưa vào các getter mới `feature()`, `interim()`, `update()` và `patch()`.

Điểm trọng tâm:

- **`FEATURE`** phản ánh đợt phát hành tính năng, không phải một “major compatibility version” theo cách hiểu cũ.
- **`INTERIM`** dành cho một lớp phát hành trung gian nếu mô hình phát hành có dùng. Trong lịch phát hành sáu tháng được mô tả bởi JEP 322, thành phần này thường là 0.
- **`UPDATE`** dành cho bản cập nhật sửa lỗi, bảo mật, hồi quy và các vấn đề được phát hiện.
- **`PATCH`** dành cho bản vá khẩn cấp đối với vấn đề nghiêm trọng.
- Phần **pre-release / build / optional** mang thông tin thêm về bản build, thử nghiệm sớm hoặc nhận diện riêng của nhà phân phối.

**Không cần cài JDK 10 để học nội dung này.** Mọi ví dụ dùng Java 17+ vẫn hợp lệ vì mô hình và API tiếp tục được duy trì. Hạn chế dùng các accessor cũ `major()`, `minor()` và `security()` trong mã mới: chúng đã được đánh dấu deprecated từ Java 10; thay bằng `feature()`, `interim()` và `update()`.

### 2.1. Số FEATURE không đơn giản là số lượng tính năng

`FEATURE=21` không mang nghĩa “có đúng 21 tính năng mới”. Nó là **bộ đếm đợt phát hành feature**. Dòng phát hành Java SE thường tăng FEATURE theo nhịp sáu tháng. Một phiên bản có FEATURE lớn hơn có thể có thay đổi API, ngôn ngữ hoặc hành vi, nhưng chính số này không cho biết mọi tính năng cụ thể.

Cũng không được kết luận rằng một JDK có FEATURE mới nhất tự động đáp ứng chính sách hỗ trợ dài hạn của công ty. Chính sách hỗ trợ/bảo mật phụ thuộc nhà phân phối, update thực tế, license và lịch vá lỗi.

## 3. `$VNUM`: số phiên bản có cấu trúc như thế nào?

Theo JEP 322 và Javadoc `Runtime.Version`, `$VNUM` là **một hoặc nhiều số nguyên không âm** cách nhau bằng dấu chấm, trong đó:
- Thành phần đầu tiên là số nguyên **dương**, không có số 0 đứng trước.
- Thành phần số ở giữa có thể là `0`.
- Thành phần cuối cùng của số phiên bản **không được bằng 0**.
- Các thành phần dương không có leading zero.
- Số thành phần có thể dài hơn bốn; ý nghĩa chính thức của **bốn thành phần đầu** được đặt tên theo JEP 322.

Biểu thức hình dạng theo Javadoc (đây là regex **minh họa phần `$VNUM`**, không phải regex parse cả chuỗi pre/build/optional):

```regex
[1-9][0-9]*((\.0)*\.[1-9][0-9]*)*
```

Đừng viết một parser JDK riêng chỉ dựa trên regex này khi `Runtime.Version.parse` đã có sẵn. Regex chủ yếu giúp hiểu tại sao các số 0 **ở giữa** hợp lệ còn số 0 **ở cuối** bị loại.

### 3.1. Bốn thành phần có ý nghĩa cố định

| Thành phần | Vị trí trong `$VNUM` | Diễn giải theo JEP 322 | Ví dụ |
| --- | ---: | --- | --- |
| `FEATURE` | 1 | Bộ đếm bản phát hành feature; tăng cho mỗi đợt phát hành feature | `21` trong `21.0.2` |
| `INTERIM` | 2 | Bộ đếm bản phát hành trung gian tương thích nếu mô hình có dùng | `0` trong `21.0.2` |
| `UPDATE` | 3 | Bộ đếm bản cập nhật sửa lỗi, bảo mật và hồi quy | `2` trong `21.0.2` |
| `PATCH` | 4 | Bộ đếm bản vá khẩn cấp | `1` trong `21.0.2.1` |
| Thành phần 5+ | 5 trở đi | Dành cho nhu cầu bổ sung của các downstream implementors | `7` trong `21.0.2.1.7` |

Đối với `21.0.2+13`: **`FEATURE=21`, `INTERIM=0`, `UPDATE=2`, `PATCH=0`**. Dấu `+13` là **số build**, không phải PATCH. Không được lấy số sau dấu `+` làm phần thứ tư của `$VNUM`.

Đối với `21.0.2.1`: **`PATCH=1`**. Dấu chấm và dấu cộng mang ý nghĩa khác nhau.

### 3.2. Thành phần 0 ở giữa và việc bỏ số 0 cuối

| Chuỗi `$VNUM` | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `21` | Có | FEATURE 21; các getter còn lại trả 0 |
| `21.0.2` | Có | INTERIM 0 nằm giữa FEATURE và UPDATE 2 |
| `21.0.2.1` | Có | PATCH 1 |
| `21.0.2.1.7` | Có | Thành phần bổ sung của downstream distribution |
| `21.0` | Không | Số phiên bản kết thúc bằng thành phần 0 |
| `21.0.0` | Không | Số phiên bản kết thúc bằng 0 |
| `21.0.2.0` | Không | PATCH bằng 0 ở cuối; phần đó phải được bỏ |
| `021` | Không | Thành phần dương có leading zero |
| `21.00.2` | Không | Thành phần 0 phải viết `0`, không phải `00` |
| `21..2` | Không | Có thành phần rỗng giữa hai dấu chấm |
| `0` | Không | FEATURE không thể bằng 0 |

Đọc **số phiên bản** đúng nghĩa: `21.0.2` và khái niệm `21.0.2.0` có thể mô tả cùng bốn giá trị số học khi điền thành phần thiếu, nhưng **`21.0.2.0` không phải một chuỗi phiên bản hợp lệ để truyền vào `parse`**. Không đưa chuỗi có trailing zero vào danh sách accepted versions.

### 3.3. Tại sao `version()` chỉ trả những phần thực sự có trong chuỗi?

`Runtime.Version.parse("21").version()` trả danh sách `[21]`, không phải `[21, 0, 0, 0]`. Trong khi đó:
- `feature() == 21`
- `interim() == 0`
- `update() == 0`
- `patch() == 0`

`version()` là **danh sách các số có trong `$VNUM`**, và theo Javadoc là **unmodifiable List**. Các accessor `interim/update/patch` trả 0 nếu phần đó vắng mặt. Nếu cần bốn cột ở báo cáo, dùng bốn getter; nếu cần giữ cấu trúc số nguyên được công bố, dùng `version()`.

Không đồng nhất “trong danh sách thiếu phần tử” với “phiên bản parser không hợp lệ”.

## 4. `$VSTR`: chuỗi phiên bản đầy đủ

Một **version string** có thể bao gồm:
- `$VNUM`: phần số phiên bản.
- `$PRE`: thông tin **pre-release** như `ea` (*early access*).
- `$BUILD`: số build được quảng bá.
- `$OPT`: thông tin bổ sung tùy chọn của bản build/nhà phân phối, chẳng hạn `LTS`.

Các dạng hợp lệ được Javadoc mô tả khái quát:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
```

Trong biểu thức này:
- `$PRE`: chuỗi chữ cái/chữ số (`[a-zA-Z0-9]+`).
- `$BUILD`: số nguyên không âm **không có leading zero** ngoại trừ chính `0`.
- `$OPT`: thông tin thêm gồm chữ cái, số, dấu gạch nối hoặc dấu chấm theo khuôn dạng được Javadoc chấp nhận.
- Dấu `-` trước `$PRE` **khác** dấu `-` trước `$OPT`, vì vị trí và dấu `+` quyết định cách parse.
- `$OPT` không bắt buộc có; `$BUILD` có thể không xuất hiện trong một số dạng.

### 4.1. Bảng đọc chuỗi theo từng thành phần

| Chuỗi minh họa | `$VNUM` | `$PRE` | `$BUILD` | `$OPT` |
| --- | --- | --- | --- | --- |
| `21` | `21` | Không | Không | Không |
| `21.0.2` | `21.0.2` | Không | Không | Không |
| `21.0.2.1` | `21.0.2.1` | Không | Không | Không |
| `21-ea` | `21` | `ea` | Không | Không |
| `21-ea+28` | `21` | `ea` | `28` | Không |
| `21.0.2+13` | `21.0.2` | Không | `13` | Không |
| `21.0.2+13-LTS` | `21.0.2` | Không | `13` | `LTS` |
| `21+-LTS` | `21` | Không | Không | `LTS` |

Các chuỗi này được dùng như **ví dụ phân tích cú pháp**. Việc `parse` chấp nhận một chuỗi không chứng minh rằng đã có bản phát hành thực tế mang chính xác số build, metadata hoặc nhà phân phối đó.

### 4.2. Phân biệt `21-ea` và `21+-ea`

Theo Javadoc:
- `21-ea`: `PRE=ea`, là thông tin **pre-release**.
- `21+-ea`: `OPT=ea`, là **optional build information**.

Cùng có chữ `ea` nhưng **khác trường và khác ảnh hưởng khi so sánh**. Dấu `+` quyết định vùng cú pháp và không được tùy ý bỏ hoặc thêm khi tái tạo chuỗi phiên bản. Đây cũng là lý do không thể phân tách bằng `split("-")` rồi coi mọi phần sau dấu trừ là “nhãn pre-release”.

### 4.3. `LTS` là optional metadata, không phải một thành phần số

`21.0.2+13-LTS` có `OPT=LTS`. Theo JEP 322, bên triển khai có thể bắt đầu `OPT` bằng `LTS` để truyền thông rằng bản phát hành thuộc chuỗi được nhà phân phối hỗ trợ dài hạn.

**Giới hạn rất quan trọng:** sự có mặt của `-LTS` **không phải hợp đồng Java SE bảo đảm hệ thống đã được cấp bản vá an ninh, quyền nhận support hoặc thời hạn hỗ trợ cụ thể**. Những điều đó phải kiểm tra tại nhà phân phối và chính sách tổ chức. Ngược lại, không có hậu tố `-LTS` cũng không đủ để kết luận ngay rằng bản JDK đang chạy không được bất kỳ bên nào hỗ trợ.

`$OPT` là metadata phiên bản, **không phải số PATCH hoặc UPDATE**. Đừng kiểm tra “mới hơn” bằng cách lấy số lượng ký tự của `LTS` hoặc mặc định có nhãn là ưu tiên tuyệt đối hơn mọi bản không có nhãn.

## 5. Các chuỗi phiên bản và banner có thể trông khác nhau

Trên máy có JDK, các lệnh sau là cách xem thông tin thực tế:

```bash
java --version
java -version
javac -version
```

- `java --version` / `java -version` cho biết **runtime được lệnh `java` đó gọi** cùng các dòng mô tả runtime/VM.
- `javac -version` cho biết **trình biên dịch `javac` đó**.
- `Runtime.version()` cho biết phiên bản Java **đang chạy trong JVM của ứng dụng**.
- `System.getProperty("java.version")` chứa một biểu diễn phiên bản runtime theo cấu hình của JDK.
- `System.getProperty("java.version.date")` là ngày phiên bản theo định dạng ISO 8601 `YYYY-MM-DD`, được JEP 322 bổ sung.
- `System.getProperty("java.vendor.version")` có thể được nhà phân phối gán; **không được giả định luôn có giá trị**.

**Không lấy toàn bộ banner từ `java --version` đưa thẳng vào `Runtime.Version.parse`.** Banner thường gồm nhiều dòng, tên hãng, tên VM và text mô tả. API parser nhận một **version string**, không phải thông tin marketing/tên file installer.

Tương tự, tên package phát hành của một vendor có thể chứa thêm tên hệ điều hành, kiến trúc, JDK hay JRE. Không được giả định tên file tar/zip/installer là chính xác một `$VSTR`.

### 5.1. Ví dụ đọc runtime trong chương trình

```java
Runtime.Version running = Runtime.version();
System.out.println("Running Java feature: " + running.feature());
System.out.println("Full runtime version: " + running);
System.out.println("Version date: "
        + System.getProperty("java.version.date"));
System.out.println("Vendor: " + System.getProperty("java.vendor"));
```

Đây là **đoạn nằm bên trong phương thức**; các giá trị thực tế phụ thuộc JDK đang chạy nên **không thể đưa ra một stdout cố định cho mọi máy**. Trong bài lab chính, ta chỉ in một điều kiện không phụ thuộc số feature cụ thể của JDK 17+, còn các cấu trúc phiên bản được tạo từ chuỗi hằng đã biết.

### 5.2. Đừng so sánh toàn bộ `java.version` với `Runtime.version().toString()` như một tiêu chí phổ quát

Chẳng hạn trên một JDK, `Runtime.version()` có thể chứa build metadata còn `System.getProperty("java.version")` biểu thị số phiên bản ngắn hơn. Điều này không có nghĩa runtime khác feature. Cần xem **hợp đồng từng thuộc tính**.

Nếu mục đích là kiểm tra feature version, dùng `Runtime.version().feature()`. Nếu mục đích là báo cáo build cụ thể, dùng `Runtime.version().toString()` cùng vendor/date khi phù hợp. Không tự nối `java.version` với `java.vendor.version` rồi mặc định kết quả là `$VSTR` hợp lệ.

### 5.3. Java đang chạy và Java dùng để biên dịch có thể khác

Trong môi trường build, đường dẫn `java` và `javac` có thể trỏ tới các JDK khác nhau; tool build như Maven/Gradle cũng có thể dùng **toolchain** khác với shell của người dùng. Để debug:
- Kiểm tra cả `java --version` và `javac -version`.
- Xác định JDK thật sự dùng trong build runner và runtime container.
- Khi yêu cầu bytecode tương thích một Java feature, sử dụng `javac --release N` theo cấu hình build phù hợp, thay vì chỉ đặt source level rồi mặc định JDK runtime bất kỳ sẽ chạy được.
- Không kết luận “đã chạy JDK FEATURE mới” chỉ vì một bản JDK khác được cài đâu đó trên máy.

## 6. API `Runtime.Version`: đọc trường thay vì cắt chuỗi

`Runtime.Version` là lớp biểu diễn phiên bản có hỗ trợ parse, so sánh và truy xuất các trường. Mặc dù **lớp có từ Java 9**, bốn accessor `feature/interim/update/patch` được thêm ở Java 10 để thể hiện rõ JEP 322.

| Phương thức | Kiểu trả về | Vai trò |
| --- | --- | --- |
| `Runtime.Version.parse(String)` | `Runtime.Version` | Parse và validate một chuỗi phiên bản theo grammar |
| `Runtime.version()` | `Runtime.Version` | Lấy phiên bản runtime Java hiện tại |
| `feature()` | `int` | Số FEATURE |
| `interim()` | `int` | Số INTERIM hoặc 0 khi thiếu |
| `update()` | `int` | Số UPDATE hoặc 0 khi thiếu |
| `patch()` | `int` | Số PATCH hoặc 0 khi thiếu |
| `version()` | `List<Integer>` unmodifiable | Các thành phần số thực sự có mặt trong `$VNUM` |
| `pre()` | `Optional<String>` | Pre-release ID, nếu có |
| `build()` | `Optional<Integer>` | Build number, nếu có |
| `optional()` | `Optional<String>` | Additional optional build info, nếu có |
| `compareTo(Version)` | `int` | So sánh toàn bộ thứ tự ưu tiên |
| `compareToIgnoreOptional(Version)` | `int` | So sánh nhưng bỏ `$OPT` |
| `equals(Object)` | `boolean` | Bình đẳng toàn bộ phiên bản |
| `equalsIgnoreOptional(Object)` | `boolean` | Bình đẳng bỏ `$OPT` |
| `toString()` | `String` | Chuỗi đại diện của phiên bản |

Ví dụ:

```java
var v = Runtime.Version.parse("21.0.2+13-LTS");

int feature = v.feature();          // 21
int interim = v.interim();          // 0
int update = v.update();            // 2
int patch = v.patch();              // 0
var build = v.build();              // Optional chứa 13
var pre = v.pre();                  // Optional.empty()
var optional = v.optional();        // Optional chứa "LTS"
var components = v.version();       // [21, 0, 2]
```

Mã này là ví dụ **bên trong một phương thức**. `build()` và `optional()` trả `Optional`, vì thông tin đó **không bắt buộc có**. Không được dùng `v.build().get()` nếu bạn chưa chắc có build.

### 6.1. Cách viết điều kiện có version tối thiểu

Nếu một ứng dụng cần JVM có Java FEATURE ít nhất 17:

```java
if (Runtime.version().feature() < 17) {
    throw new IllegalStateException(
            "This application requires Java 17 or newer");
}
```

Kiểm tra này nói về **feature level đang chạy**, không phải số update/bản vá an ninh. Khi ứng dụng dùng API chỉ có từ một FEATURE nhất định, cần bảo đảm **cả runtime thực tế** và **cấu hình compiler** phù hợp. Nếu biên dịch một class bằng bytecode quá mới rồi chạy trên JVM cũ, lỗi có thể xảy ra trước cả khi đoạn kiểm tra trên được thực thi.

Với kiểm tra tối thiểu bao gồm UPDATE, dùng chính sách nêu rõ ví dụ “trong cùng FEATURE thì phải ít nhất UPDATE nào”; không tự ghép chuỗi so sánh từ điển.

### 6.2. Đừng chọn getter deprecated trong mã mới

Trước khi có JEP 322, các tên `major()`/`minor()`/`security()` mang ý nghĩa lịch sử khác. Chúng đã được **deprecated từ Java 10** nhưng còn tồn tại để tương thích. Bài học hiện đại nên dùng:
- `feature()` thay `major()`.
- `interim()` thay `minor()`.
- `update()` thay `security()`.
- `patch()` cho bản vá khẩn cấp.

Không biến `update()` thành một thước đo chung “mức bảo mật có bao nhiêu điểm”; nó là **bộ đếm phát hành**, còn độ an toàn thực tế liên quan vendor và bản vá.

## 7. So sánh phiên bản: các số theo từng thành phần, không phải text

### 7.1. Vì sao so sánh từ điển sai?

`"21.0.10".compareTo("21.0.9")` ở cấp chuỗi cho kết quả không theo quy tắc số học mong muốn vì ký tự `'1'` của phần `10` nhỏ hơn `'9'`. Nhưng `Runtime.Version` so sánh từng thành phần **theo số nguyên**:

```java
Runtime.Version a = Runtime.Version.parse("21.0.10");
Runtime.Version b = Runtime.Version.parse("21.0.9");

System.out.println(a.compareTo(b) > 0); // true
```

Điều tương tự áp dụng khi có PATCH, PRE, BUILD và OPT. Không xử lý bằng cách chia chuỗi tại mỗi dấu chấm rồi tự so số, bởi các phần `+...` và `-...` có semantics riêng.

### 7.2. Thứ tự ưu tiên của `compareTo`

Javadoc quy định thứ tự xét:

1. **Các thành phần số** trong `$VNUM` theo thứ tự và giá trị.
2. **Pre-release `$PRE`:** phiên bản có PRE được coi là **nhỏ hơn** cùng số phiên bản không có PRE.
3. **Build number `$BUILD`:** không có BUILD được coi là nhỏ hơn có BUILD; nếu có cả hai thì so theo số.
4. **Optional information `$OPT`:** so theo thứ tự từ điển; nếu các trường trước bằng nhau thì có OPT được coi là lớn hơn không OPT.

Ví dụ được kiểm chứng:

```java
var ea = Runtime.Version.parse("21-ea+28");
var ga = Runtime.Version.parse("21");
System.out.println(ea.compareTo(ga) < 0); // true

var patch = Runtime.Version.parse("21.0.2.1");
var update = Runtime.Version.parse("21.0.2");
System.out.println(patch.compareTo(update) > 0); // true

var withBuild = Runtime.Version.parse("21.0.2+13");
System.out.println(
        withBuild.compareTo(update) > 0); // true
```

**Cảnh báo:** thứ tự do `Runtime.Version.compareTo` định nghĩa là một thứ tự của **chuỗi phiên bản Java**, không phải tất cả các quy tắc SemVer 2.0.0. Đặc biệt, **BUILD và OPT có ảnh hưởng tới so sánh** trong API Java này. Đừng lấy thư viện SemVer chung rồi mặc định sẽ cho cùng mọi kết quả.

### 7.3. `compareToIgnoreOptional` và `equalsIgnoreOptional`

Khi hai phiên bản chỉ khác thông tin `$OPT`:

```java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13");

System.out.println(a.equals(b));                         // false
System.out.println(a.equalsIgnoreOptional(b));           // true
System.out.println(a.compareToIgnoreOptional(b) == 0);   // true
```

`equalsIgnoreOptional` chỉ bỏ **optional build information**, **không bỏ** `$PRE`, `$BUILD` hoặc `$VNUM`. Nếu ứng dụng cần phân biệt bản build thật, dùng `equals`/`compareTo`; nếu chỉ muốn bỏ nhãn của vendor, dùng cặp IgnoreOptional một cách nhất quán.

Không nên dùng `compareToIgnoreOptional` làm comparator của `TreeSet` rồi kiểm tra “trùng” bằng `equals` và kỳ vọng cùng một tập quan hệ bằng nhau. Comparator coi hai bản khác `$OPT` là bằng nhau dù `equals` không; phải thiết kế rõ mục đích của collection.

### 7.4. Early access không thể được chọn chỉ bằng FEATURE

Hai chuỗi `21-ea+28` và `21` đều có `feature()==21`. Nhưng `pre()` của bản đầu chứa `"ea"`, còn bản thứ hai rỗng.

Nếu ứng dụng yêu cầu **bản phát hành ổn định (GA)**, không nên chỉ kiểm tra `feature() >= 21`. Cần thêm chính sách về `pre().isPresent()`, lựa chọn vendor, bản phát hành ổn định thực tế và môi trường chạy. `pre().isEmpty()` nói rằng **không có pre-release marker** trong phiên bản, nhưng không thay thế mọi kiểm chứng về chất lượng sản phẩm hay support.

## 8. Cú pháp nào hợp lệ và ngoại lệ nào xảy ra?

`Runtime.Version.parse(String)` xác minh toàn bộ chuỗi theo grammar của JDK. Javadoc quy định:

- **`IllegalArgumentException`** nếu chuỗi không diễn giải được thành phiên bản hợp lệ.
- **`NullPointerException`** nếu input là `null`.
- **`NumberFormatException`** nếu một thành phần số hoặc build number không biểu diễn được dưới dạng `Integer`. Đây là subtype của `IllegalArgumentException`.

Ví dụ các input cố ý sai:

| Input | Vấn đề |
| --- | --- |
| `""` | Chuỗi rỗng |
| `021` | FEATURE có leading zero |
| `21.0` | `$VNUM` có trailing zero |
| `21.0.0` | `$VNUM` có trailing zero |
| `21..2` | Một thành phần giữa bị rỗng |
| `21.0.2+03` | BUILD có leading zero |
| `999999999999999999999999` | Thành phần số vượt miền `Integer` |

Một cách xử lý tại boundary config:

```java
static Runtime.Version parseVersionOrReject(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "JDK version must not be blank");
    }
    try {
        return Runtime.Version.parse(value);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Unsupported JDK version string: " + value, ex);
    }
}
```

Đây là **một phương thức minh họa trong class**. Phân loại invalid syntax đúng nghĩa không đồng nghĩa version thấp hơn yêu cầu. `"21.0.0"` là input **sai cú pháp**, không nên tự sửa ngầm thành `"21"` khi người dùng/CI yêu cầu kiểm tra string chính xác.

### 8.1. Giới hạn của `parse`

`Runtime.Version.parse("21.0.2+13-LTS")` thành công chỉ cho thấy chuỗi **đúng cấu trúc**, không chứng minh:
- Một nhà phân phối thực sự đã phát hành chính xác bản build đó.
- Bản build tồn tại trên máy người dùng.
- Bản build đã được tổ chức phê duyệt.
- Bản build nhận bản vá bảo mật mới nhất hoặc có hợp đồng hỗ trợ.
- Chuỗi được lấy từ nguồn đáng tin cậy.

Có thể parse cả một phiên bản **tương lai** hoặc một phiên bản không có bản phân phối tương ứng, miễn chuỗi hợp lệ.

## 9. Dữ liệu không nên bị hiểu nhầm thành chuỗi phiên bản chuẩn

### 9.1. `java.version.date` là một **ngày**, không phải `$VNUM`

`System.getProperty("java.version.date")` dùng định dạng ISO `YYYY-MM-DD`. Đó là thông tin về ngày phiên bản, phục vụ việc hiểu thời điểm phát hành; nó không thay các số `UPDATE`/`PATCH`. Nếu muốn phân tích ngày, dùng `java.time.LocalDate.parse` với dữ liệu hợp lệ, không dùng `Runtime.Version.parse`.

Một bản JDK phát hành gần đây hơn chưa chắc đã là bản duy nhất được hỗ trợ bảo mật, vì các dòng LTS có nhiều update. Đừng chỉ so hai chuỗi `java.version.date` của hai FEATURE khác nhau rồi suy diễn bảo đảm tương thích hoặc support.

### 9.2. `java.vendor.version` thuộc sản phẩm của vendor

Nhà phân phối có thể có version string riêng cho sản phẩm, được biểu diễn qua `java.vendor.version` nếu có. Thuộc tính ấy **không nhất thiết là một `$VSTR` hợp lệ của Java SE**.

Ví dụ một vendor dùng số product theo năm/tháng. Không bắt buộc `Runtime.Version.parse` phải phân tích được format của vendor. Khi quản lý inventory, lưu riêng:
- `Runtime.version().toString()`.
- `java.vendor`.
- `java.vendor.version` nếu có.
- `java.version.date`.
- Nền tảng/kiến trúc và nguồn phân phối theo cơ chế kiểm kê của tổ chức.

Đừng gộp tất cả thành một chuỗi duy nhất rồi so sánh bằng text.

### 9.3. Version của compiler, class file và runtime là ba khái niệm

`javac -version` có thể báo Java FEATURE dùng để biên dịch. `Runtime.version()` phản ánh runtime Java đang chạy. Còn **class-file major version** (ví dụ 61 cho Java 17) có một hệ đánh số riêng; không phải `FEATURE=61` của JDK.

Đừng parse class-file version bằng `Runtime.Version.parse` để suy ra feature JDK. Khi cần phân tích bytecode, sử dụng công cụ/lớp tài liệu phù hợp với class-file format.

## 10. Chương trình Java hoàn chỉnh, có thể chạy ngay

### 10.1. Chuẩn bị

Dùng **JDK 17+ đang được nhà cung cấp hỗ trợ/cập nhật bản vá**; thực hành trên JDK 21 hoặc 25 theo chính sách môi trường. Những bản số trong code như `21` hoặc `21.0.2+13-LTS` là **test fixtures**, không bắt buộc trùng phiên bản JDK đang cài.

```bash
java -version
javac -version
```

Tạo tệp đúng tên **`VersionStringLab.java`** với nội dung sau:

```java
public class VersionStringLab {
    static void reject(String value, String label) {
        try {
            Runtime.Version.parse(value);
            System.out.println(label + ": false");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": true");
        }
    }

    public static void main(String[] args) {
        Runtime.Version full =
                Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version plainBuild =
                Runtime.Version.parse("21.0.2+13");
        Runtime.Version bare =
                Runtime.Version.parse("21");
        Runtime.Version preview =
                Runtime.Version.parse("21-ea+28");
        Runtime.Version patched =
                Runtime.Version.parse("21.0.2.1");

        // Số phiên bản và bốn accessor của JEP 322.
        System.out.println("version components: "
                + full.version());
        System.out.println("feature: " + full.feature());
        System.out.println("interim: " + full.interim());
        System.out.println("update: " + full.update());
        System.out.println("patch: " + full.patch());
        System.out.println("pre: "
                + full.pre().orElse("none"));
        System.out.println("build: "
                + full.build().orElse(-1));
        System.out.println("optional: "
                + full.optional().orElse("none"));

        // Các thành phần vắng mặt không được điền vào List.
        System.out.println("bare version components: "
                + bare.version());
        System.out.println("bare update accessor: "
                + bare.update());

        // Pre-release và các quy tắc so sánh.
        System.out.println("EA identifier: "
                + preview.pre().orElse("none"));
        System.out.println("EA before GA: "
                + (preview.compareTo(bare) < 0));
        System.out.println("numeric 10 > 9: "
                + (Runtime.Version.parse("21.0.10")
                        .compareTo(
                                Runtime.Version.parse("21.0.9")) > 0));
        System.out.println("patch > update: "
                + (patched.compareTo(
                        Runtime.Version.parse("21.0.2")) > 0));
        System.out.println("build > no build: "
                + (plainBuild.compareTo(
                        Runtime.Version.parse("21.0.2")) > 0));

        // OPT khác nhau vẫn có thể bỏ qua có chủ đích.
        System.out.println("optional affects equals: "
                + full.equals(plainBuild));
        System.out.println("ignore optional equals: "
                + full.equalsIgnoreOptional(plainBuild));
        System.out.println("ignore optional compare: "
                + (full.compareToIgnoreOptional(plainBuild) == 0));
        System.out.println("optional > none: "
                + (full.compareTo(plainBuild) > 0));

        // Chỉ đặt điều kiện phù hợp JDK 17+ dùng để chạy lab.
        System.out.println("runtime feature >= 17: "
                + (Runtime.version().feature() >= 17));

        // Input không hợp lệ phải bị từ chối, không tự sửa ngầm.
        reject("21.0.0", "reject trailing zero");
        reject("021", "reject leading zero");
        reject("21..2", "reject missing component");
        reject("21.0.2+03", "reject leading zero build");
        reject("", "reject empty input");

        try {
            Runtime.Version.parse(null);
        } catch (NullPointerException ex) {
            System.out.println("null input: NullPointerException");
        }

        // Optional information có thể có dù thiếu build.
        Runtime.Version optionalOnly =
                Runtime.Version.parse("21+-LTS");
        System.out.println("optional without build: "
                + optionalOnly.optional().orElse("none"));
        System.out.println("build absent with optional: "
                + optionalOnly.build().isEmpty());

        // Thành phần thứ năm dành cho downstream implementor.
        Runtime.Version extended =
                Runtime.Version.parse("21.0.2.1.7");
        System.out.println("extended numeric component count: "
                + extended.version().size());
    }
}
```

### 10.2. Biên dịch và chạy

Trong thư mục có tệp:

```bash
javac VersionStringLab.java
java VersionStringLab
```

### 10.3. Stdout chuẩn (29 dòng)

```text
version components: [21, 0, 2]
feature: 21
interim: 0
update: 2
patch: 0
pre: none
build: 13
optional: LTS
bare version components: [21]
bare update accessor: 0
EA identifier: ea
EA before GA: true
numeric 10 > 9: true
patch > update: true
build > no build: true
optional affects equals: false
ignore optional equals: true
ignore optional compare: true
optional > none: true
runtime feature >= 17: true
reject trailing zero: true
reject leading zero: true
reject missing component: true
reject leading zero build: true
reject empty input: true
null input: NullPointerException
optional without build: LTS
build absent with optional: true
extended numeric component count: 5
```

Output này **không in số Java đang chạy**, ngoài kiểm tra điều kiện JDK 17+ đã nêu. Vì thế không thay đổi theo tên vendor, build thực tế hoặc ngày cập nhật của runtime. Phần lớn output do `Runtime.Version.parse` xử lý các fixtures cố định và đã được kiểm chứng bằng JShell trên JDK hiện đại.

### 10.4. Giải thích những dòng quan trọng

**Dòng 1–8:** `21.0.2+13-LTS` được tách thành `$VNUM=21.0.2`, FEATURE 21, INTERIM 0, UPDATE 2, PATCH 0. `pre()` rỗng, `build()` chứa 13, `optional()` chứa `LTS`.

**Dòng 9–10:** `21` có danh sách thành phần số chỉ `[21]` nhưng getter `update()` vẫn trả 0. Đây là lý do không đọc vị trí thứ ba từ `version().get(2)` mà không kiểm tra kích thước.

**Dòng 11–12:** `21-ea+28` có `pre=ea` và được sắp trước phiên bản `21` không có pre-release marker. Không đồng nhất hai phiên bản chỉ vì `feature()==21`.

**Dòng 13–15:** `21.0.10` lớn hơn `21.0.9` theo **số**, `21.0.2.1` lớn hơn `21.0.2` theo PATCH, và `21.0.2+13` lớn hơn `21.0.2` theo quy tắc BUILD của `compareTo`.

**Dòng 16–19:** Hai chuỗi cùng số và build nhưng khác `OPT` không bằng nhau theo `equals`; chúng bằng nhau theo `equalsIgnoreOptional` và bằng nhau về thứ tự theo `compareToIgnoreOptional`. Khi so đầy đủ, có `OPT` được đặt sau không có `OPT` nếu các trường trước bằng nhau.

**Dòng 20:** Lab yêu cầu chạy trên JDK 17+, nên `Runtime.version().feature() >= 17` là `true`. Đây là kiểm tra đang chạy trên một feature phù hợp, không xác nhận build đó an toàn trước mọi lỗ hổng.

**Dòng 21–25:** Các input có trailing zero, leading zero, thành phần rỗng, BUILD viết sai hoặc chuỗi rỗng được `parse` từ chối bằng `IllegalArgumentException`. Hàm `reject` trả `true` khi đã bắt được trường hợp không hợp lệ.

**Dòng 26:** Input `null` gây `NullPointerException`, được bắt riêng; không xem đó là một phiên bản hợp lệ.

**Dòng 27–28:** `21+-LTS` là dạng có `OPT` mà không có `BUILD`. `build().isEmpty()==true` chứng minh optional metadata và số build là hai trường độc lập.

**Dòng 29:** `21.0.2.1.7` có năm phần số; bốn phần đầu tương ứng `FEATURE/INTERIM/UPDATE/PATCH`, còn phần thứ năm dành cho downstream consumer.

## 11. Ứng dụng thực tế: kiểm tra JDK phiên bản tối thiểu

### 11.1. Chỉ cần Java feature tối thiểu

Ứng dụng dùng API được bổ sung từ Java FEATURE 21 có thể kiểm tra:

```java
static void requireFeatureAtLeast(int minimum) {
    int running = Runtime.version().feature();
    if (running < minimum) {
        throw new IllegalStateException(
                "Required Java feature >= " + minimum
                + ", current feature: " + running);
    }
}
```

Đây là **đoạn minh họa** đặt trong class. Kiểm tra này chỉ thật sự chạy nếu JVM đã nạp được class; vẫn cần cấu hình build/deployment phù hợp. Một class được biên dịch ra bytecode không tương thích sẽ không thể được cứu bằng check trong `main` khi JVM cũ từ chối nạp class.

### 11.2. Ràng buộc update theo một nhánh FEATURE

Nếu dự án biết **một nhánh Java cụ thể** cần tối thiểu update `21.0.2`, nên diễn đạt rõ “trong FEATURE 21, phải ít nhất 21.0.2” và chính sách khi chạy FEATURE mới hơn:

```java
static boolean meetsMinimum(Runtime.Version running) {
    Runtime.Version minimum =
            Runtime.Version.parse("21.0.2");
    return running.feature() > minimum.feature()
            || (running.feature() == minimum.feature()
                    && running.compareTo(minimum) >= 0);
}
```

**Lưu ý:** `compareTo` còn xét PRE/BUILD/OPT. Nếu business rule chỉ quan tâm FEATURE/UPDATE/PATCH và phải **loại bản EA**, nên lập điều kiện thành phần riêng, có kiểm tra `pre().isEmpty()`, và xác minh theo vendor release policy. Đừng mặc định một biểu thức `compareTo >= 0` luôn là policy security đủ dùng.

Các bản cập nhật của nhánh khác có **lịch phát hành/bảo mật riêng**. Không suy luận JDK FEATURE 25 luôn thay thế hoàn toàn chính sách tối thiểu của nhánh FEATURE 21 chỉ bằng một phép so sánh số học.

### 11.3. Policy về pre-release

Nếu production không cho phép phiên bản EA:

```java
Runtime.Version running = Runtime.version();
if (running.pre().isPresent()) {
    throw new IllegalStateException(
            "Pre-release Java runtime is not allowed");
}
```

Điều kiện này đọc **marker PRE**, không scan substring `"-ea"` trên tên bundle. Một vendor có thể ghi metadata riêng; hãy xem thêm `java.vendor` và manifest phân phối nếu chính sách yêu cầu, chứ không suy ra mọi chi tiết từ `OPT`.

### 11.4. Khác biệt giữa ngưỡng API và SLA hỗ trợ

Hai ràng buộc cần được quản lý riêng:
- **Tương thích API/bytecode:** xem FEATURE, toolchain, `--release`, preview features nếu có.
- **Mức bản vá và hỗ trợ:** xem UPDATE/PATCH, ngày, nhà phân phối và danh sách bản build đã được phê duyệt.

`-LTS` là một dấu hiệu metadata của bên triển khai, không thay thế hợp đồng support. Một policy an toàn có thể sử dụng allowlist vendor + version/build cập nhật, thay vì “có chữ LTS trong output thì an toàn”.

## 12. Thiết kế parser, comparator và logging cho công cụ quản lý JDK

### 12.1. Một pipeline xử lý nên tách bốn bước

```text
Nhận version string tin cậy / bản scan cài đặt
             |
             v
Runtime.Version.parse(...)
             |
   +---------+----------+
   | parse fail         | parse success
   v                    v
Báo lỗi cú pháp      Đọc feature/interim/update/patch
                       |
                       v
                 Đọc pre/build/optional
                       |
                       v
               Áp dụng chính sách
             (min version, EA, vendor)
                       |
                       v
                   Báo cáo rõ
               requested / parsed /
               runtime / vendor / date
```

Kết quả parse nên được lưu như một `Runtime.Version` (hoặc một cấu trúc domain nếu cần thêm vendor/support), **không chỉ lưu chuỗi rồi split để lấy token thứ ba**. Điều này giúp bảo toàn thông tin `PRE/BUILD/OPT`.

### 12.2. Cẩn thận khi dùng trong sorting hoặc map keys

`Runtime.Version` là **value-based class**. Không dùng instance cho đồng bộ bằng `synchronized(version)` hay phân biệt phiên bản qua object identity `==`. Dùng `equals` và `hashCode` cho quan hệ bình đẳng toàn phần.

Nếu bạn lập `TreeSet` với `compareToIgnoreOptional`, hai phiên bản chỉ khác `OPT` có thể trở thành **cùng một phần tử về comparator**, trong khi `equals` vẫn báo khác. Điều này có thể đúng nếu bạn muốn dedup bỏ vendor label, nhưng phải định nghĩa đó là chính sách. Không xen lẫn một comparator và một phép equals với semantics khác mà không có lý do.

### 12.3. Bảo vệ đầu vào và không phát minh dữ liệu

Khi đọc manifest của một bản JDK, metadata có thể được viết theo định dạng riêng. Chỉ gọi `Runtime.Version.parse` nếu đầu vào **thật sự là version string của Java**. Không lấy toàn bộ text `java --version`, tên zip, chuỗi `javac ...` rồi mong parser tự rút ra version.

Nếu parse thất bại, trả lỗi input và nguồn dữ liệu; đừng tự “thử lại” bằng cách xóa các ký tự bất kỳ cho tới khi parse được. Việc gọt chuỗi như vậy có thể âm thầm biến input của một sản phẩm khác thành version Java sai.

### 12.4. Logging đủ dùng nhưng không khóa cứng môi trường

Có thể ghi:
- `feature/interim/update/patch`.
- `pre/build/optional` nếu hiện diện.
- `java.vendor`, `java.vendor.version` nếu có.
- `java.version.date` để hỗ trợ kiểm kê.
- Ngày quan sát và ID runtime/container của tác vụ theo hệ thống logging.

Không phải tất cả các thuộc tính này đều có định dạng phù hợp để parse thành `Runtime.Version`. Đừng log bí mật từ đường dẫn, biến môi trường hoặc thông số người dùng khi không cần thiết.

## 13. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Coi `21.0.2+13` là FEATURE=21, UPDATE=2, PATCH=13 | Số sau `+` là BUILD | Dùng `patch()` và `build()` riêng |
| Coi `21.0.2.1` là build 1 | Thành phần sau dấu chấm thứ ba là PATCH | Dùng `patch()` |
| Viết `21.0.0` để diễn tả feature 21 | `$VNUM` không có trailing zero | Viết `21` |
| Viết `021` hoặc `21.0.2+03` | Leading zero không hợp lệ | Chuẩn hóa đầu vào ở nguồn, dùng cú pháp chuẩn |
| So sánh `"21.0.10"` và `"21.0.9"` bằng `String.compareTo` | Sai thứ tự số học | `Runtime.Version.compareTo` |
| Coi `-ea` và `+-ea` đồng nghĩa | Một bên PRE, bên kia OPT | Parse bằng `Runtime.Version.parse` |
| Coi build metadata không ảnh hưởng `compareTo` | Java có thứ tự BUILD và OPT | Đọc contract `compareTo`; không áp dụng SemVer mù |
| Coi `equalsIgnoreOptional` bỏ qua BUILD | Chỉ bỏ OPT | Dùng phép so sánh phù hợp chính sách |
| Tưởng `Runtime.Version` bắt đầu ở Java 10 | Lớp có từ Java 9 | Phân biệt API nền với các getter mới từ Java 10 |
| Tiếp tục dùng `major/minor/security` trong mã mới | Tên deprecated và không diễn đạt mô hình thời gian | Dùng `feature/interim/update` |
| Dựa vào `version().get(2)` cho chuỗi `21` | List chỉ có 1 phần tử | Dùng `update()` nếu cần 0 khi thiếu |
| Gọi `build().get()` không kiểm tra | BUILD là Optional | Dùng `orElse` hoặc `isPresent` |
| Coi `-LTS` tự chứng minh có support | Metadata do nhà phân phối cung cấp | Kiểm tra lịch support/vendor policy riêng |
| Chỉ kiểm tra `feature()` để loại EA | EA và GA có thể cùng FEATURE | Kiểm tra `pre()` và release policy |
| Đưa toàn bộ banner `java --version` vào `parse` | Parser nhận VSTR, không nhận banner | Trích dữ liệu version đúng nguồn có contract |
| So khớp tuyệt đối `java.version` với `Runtime.version().toString()` | Một biểu diễn có thể bỏ BUILD/OPT | So đúng trường hoặc dùng Runtime.version |
| Coi build JDK và runtime JDK chắc chắn giống nhau | Có thể dùng toolchain/path khác | Kiểm tra `javac -version`, `java --version`, runtime thật |
| Coi bản FEATURE cao luôn mới về security | Các nhánh, vendor và thời điểm update khác nhau | Theo chính sách bản vá cụ thể và ngày phát hành |
| Khóa cứng `Runtime.version().feature()==21` trong bài lab | Máy đọc có thể chạy JDK khác | Dùng fixtures cho output và check min version |

## 14. Bài tập tự luyện có đáp án

### Bài 1 — Phân tích một chuỗi

```text
21.0.2+13-LTS
```

**Hỏi:** FEATURE, INTERIM, UPDATE, PATCH, BUILD, OPT?

**Đáp án:** FEATURE=21, INTERIM=0, UPDATE=2, PATCH=0 (không có thành phần PATCH trong chuỗi), BUILD=13, OPT=LTS. Không có PRE.

### Bài 2 — `21.0.2.1` khác `21.0.2+1` thế nào?

**Đáp án:** `21.0.2.1` có **PATCH=1**, BUILD vắng mặt. `21.0.2+1` có **PATCH=0**, BUILD=1. Không hoán đổi `.` và `+`.

### Bài 3 — Leading zero và trailing zero

Trong `21`, `21.0.2`, `21.0`, `021`, chuỗi nào là VNUM hợp lệ?

**Đáp án:** `21` và `21.0.2`. `21.0` có trailing zero; `021` có leading zero.

### Bài 4 — Danh sách phần số và accessor

```java
Runtime.Version v = Runtime.Version.parse("21");
```

**Hỏi:** `v.version()` và `v.update()` trả gì?

**Đáp án:** `version()` trả `[21]`, `update()` trả `0`. API không điền các zero vào List nhưng getter trả zero khi thành phần thiếu.

### Bài 5 — Pre-release và GA

`21-ea+28` và `21` có FEATURE bằng nhau không? Bản nào đứng trước theo `compareTo`?

**Đáp án:** Cùng FEATURE 21. `21-ea+28` có PRE=ea nên đứng trước `21` theo `Runtime.Version.compareTo`.

### Bài 6 — So sánh số học

`21.0.10` và `21.0.9`: dùng `String.compareTo` hay `Runtime.Version.compareTo`?

**Đáp án:** Dùng `Runtime.Version.compareTo`; `21.0.10` lớn hơn vì 10 lớn hơn 9 theo số học.

### Bài 7 — BUILD và OPT

```text
21.0.2+13-LTS
21.0.2+13
```

**Hỏi:** Hai version bằng nhau theo `equals` và `equalsIgnoreOptional` không?

**Đáp án:** `equals` trả `false` vì khác OPT. `equalsIgnoreOptional` trả `true`, tương ứng `compareToIgnoreOptional()==0`.

### Bài 8 — Optional không có build

`Runtime.Version.parse("21+-LTS")` có BUILD không?

**Đáp án:** Không. `build().isEmpty()` là `true`, `optional().orElse("none")` là `LTS`. Không tự suy ra BUILD=0.

### Bài 9 — Input sai

Tại sao `Runtime.Version.parse("21.0.2+03")` bị từ chối?

**Đáp án:** BUILD number có leading zero. Chuỗi số build đúng cấu trúc phải là `3`, không phải `03`.

### Bài 10 — LTS và bảo mật

Một JDK có chuỗi kết thúc `-LTS`. Đã đủ bằng chứng rằng mọi lỗ hổng đã có bản vá và công ty sẽ được hỗ trợ đến một ngày cụ thể không?

**Đáp án:** Chưa. OPT là metadata của nhà phân phối. Cần kiểm tra nhà cung cấp, phiên bản update/patch, lịch phát hành, cảnh báo bảo mật và hợp đồng support.

### Bài 11 — Phiên bản đang chạy

`javac -version` báo một FEATURE nhưng `Runtime.version().feature()` trong ứng dụng báo FEATURE khác. Có khả năng gì?

**Đáp án:** Compiler và runtime đang dùng các đường dẫn/toolchain khác nhau, hoặc build/container chọn JDK khác shell. Cần kiểm tra JDK ở bước biên dịch và JVM ở thời điểm chạy; không đoán từ một lệnh duy nhất.

### Bài 12 — Chính sách cấm EA

Một gate chỉ viết `Runtime.version().feature() >= 21` có chặn được `21-ea+28` không?

**Đáp án:** Không, vì bản EA cũng có FEATURE 21. Thêm kiểm tra `pre().isEmpty()` nếu yêu cầu không có PRE và đối chiếu release/vendor policy khi cần tính ổn định.

### Bài 13 — Thành phần thứ năm

`Runtime.Version.parse("21.0.2.1.7").version()` có bao nhiêu phần tử? `7` có nghĩa PATCH không?

**Đáp án:** Có 5 phần tử. PATCH là thành phần thứ tư, bằng `1`; thành phần thứ năm được dành cho downstream implementors, không có tên PATCH trong mô hình bốn phần của JEP 322.

### Bài 14 — Ngày và phiên bản

`java.version.date` có dạng `2025-10-21`, có nên gọi `Runtime.Version.parse` cho chuỗi ngày đó không?

**Đáp án:** Không. Đây là ngày theo ISO `YYYY-MM-DD`, không phải JDK VSTR. Dùng `LocalDate.parse` nếu cần xử lý ngày, không xem năm là FEATURE JDK.

### Bài 15 — So sánh dùng comparator IgnoreOptional

Nếu một `TreeSet` dùng `Runtime.Version::compareToIgnoreOptional`, nó có thể coi `21.0.2+13-LTS` và `21.0.2+13` là một phần tử không?

**Đáp án:** Có, vì comparator trả `0` dù `equals` trả false. Phải quyết định rõ có muốn bỏ nhãn OPT khi dedup hay không; không trộn comparator này với các assumption về `equals`.

## 15. Checklist áp dụng vào dự án

- [ ] Đọc JEP 322, phân biệt rõ `$VNUM` và `$VSTR`.
- [ ] Biết FEATURE/INTERIM/UPDATE/PATCH có ý nghĩa từ Java 10 và các số phía sau BUILD/OPT không tự biến thành PATCH.
- [ ] Không viết thành phần 0 cuối; không viết leading zero trong các thành phần số hoặc BUILD.
- [ ] Dùng `Runtime.Version.parse` thay vì viết parser split/regex thủ công cho toàn VSTR.
- [ ] Dùng `feature/interim/update/patch`; không giới thiệu accessor deprecated cho mã mới.
- [ ] Đọc `pre/build/optional` bằng Optional, kiểm tra sự hiện diện.
- [ ] Hiểu bản EA có thể cùng FEATURE với bản GA.
- [ ] Dùng `compareTo` để so phiên bản Java theo hợp đồng của JDK.
- [ ] Dùng `compareToIgnoreOptional` **cùng** `equalsIgnoreOptional` khi muốn loại trừ đúng OPT.
- [ ] Không giả định SemVer build metadata là không quan trọng đối với `Runtime.Version.compareTo`.
- [ ] Không dựa vào hậu tố `LTS` để kết luận về support/security.
- [ ] Lấy `Runtime.version()` để kiểm tra runtime đang chạy; không lấy toàn bộ banner `java --version` làm parser input.
- [ ] Phân biệt runtime, compiler/toolchain, vendor version, version date và class-file version.
- [ ] Dùng fixtures cho unit test; không hardcode exact current JDK runtime.
- [ ] Có policies riêng cho minimum feature, minimum update, EA/GA, vendor và bản vá.
- [ ] Không dùng identity/synchronization với `Runtime.Version` value-based class.
- [ ] Chạy `VersionStringLab.java` trên JDK 17+ và đối chiếu **29 dòng stdout**.

## 16. Ghi nhớ

**Cấu trúc số phiên bản JDK hiện đại là `FEATURE.INTERIM.UPDATE.PATCH` (JEP 322 từ Java 10); chuỗi đầy đủ có thể có thêm `-PRE`, `+BUILD` và `-OPT` theo grammar của `Runtime.Version`.** Thành phần 0 cuối bị bỏ, metadata sau `+` không phải PATCH, và việc so sánh phải theo thứ tự các thành phần chứ không phải theo chuỗi ký tự.

Dùng `Runtime.version()` khi cần biết JVM đang chạy và `Runtime.Version.parse` khi kiểm tra các chuỗi version hợp lệ. Việc một chuỗi có `-LTS` hoặc một FEATURE cao hơn không tự bảo đảm chính sách vá lỗi hay hỗ trợ của nhà cung cấp. Đây là kiến thức Java 10 **vẫn còn áp dụng trên các JDK hiện đại**.

## 17. Tài liệu chính thức

- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): ý nghĩa FEATURE, INTERIM, UPDATE, PATCH; grammar, build/optional, chính sách thời gian và các system properties.
- [Oracle Java SE 25 API — Runtime.Version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): cú pháp số/chuỗi phiên bản, `parse`, accessor, `compareTo`, `compareToIgnoreOptional` và ngoại lệ.
- [Oracle Java SE 25 API — Runtime.version()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#version()): phiên bản Java runtime hiện tại.
- [Oracle JDK 25 Installation Guide — Version-String Format](https://docs.oracle.com/en/java/javase/25/install/version-string-format.html): mô hình version kể từ JDK 10, ví dụ số phiên bản và trailing zero.
- [Oracle Java SE 25 API — System.getProperties()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#getProperties()): `java.version`, `java.version.date`, `java.vendor` và `java.vendor.version`.
- [OpenJDK JEP 223 — New Version-String Scheme](https://openjdk.org/jeps/223): nguồn gốc `Runtime.Version` từ Java 9; chỉ tham khảo bối cảnh, code hiện đại dùng ngữ nghĩa JEP 322.