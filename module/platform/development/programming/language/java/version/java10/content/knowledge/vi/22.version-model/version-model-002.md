# Ý nghĩa FEATURE, INTERIM, UPDATE và PATCH trong mô hình phiên bản Java

## 1. Mục tiêu và bối cảnh Java 10

Từ **Java 10**, JDK và nền tảng Java SE sử dụng mô hình đánh số phiên bản phù hợp với nhịp phát hành dựa trên thời gian, được chuẩn hóa trong **OpenJDK JEP 322 — Time-Based Release Versioning**. Bốn thành phần đầu của số phiên bản có ý nghĩa riêng:

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

Mô hình này vẫn áp dụng trong Java hiện đại. Khi đọc các chuỗi như `21`, `21.0.2` hoặc `21.0.2.1`, cần hiểu **vị trí của từng số**, không diễn giải giống các bộ số major/minor/patch của những sản phẩm khác.

**Ví dụ minh họa, không phải lời khẳng định về bản JDK đang cài trên máy:**

| Version number | FEATURE | INTERIM | UPDATE | PATCH | Ý nghĩa về cấu trúc |
| --- | ---: | ---: | ---: | ---: | --- |
| `21` | 21 | 0 | 0 | 0 | Bản feature số 21, không có các thành phần khác được ghi |
| `21.0.1` | 21 | 0 | 1 | 0 | Bản update thứ nhất thuộc dòng feature 21 |
| `21.0.2` | 21 | 0 | 2 | 0 | Bản update thứ hai thuộc dòng feature 21 |
| `21.0.2.1` | 21 | 0 | 2 | 1 | Bản emergency patch của mức update 21.0.2 |
| `17.0.10` | 17 | 0 | 10 | 0 | Dòng feature 17, update counter 10 |
| `21.1` | 21 | 1 | 0 | 0 | Dạng số có INTERIM=1 về mặt cú pháp; không hàm ý đã có bản phát hành JDK thực tế như vậy |

**Một lưu ý quan trọng:** phiên bản ví dụ có thể **được phân tích cú pháp** mà không nhất thiết đại diện một gói JDK đã từng được phát hành. `Runtime.Version.parse` không kiểm tra kho phát hành của hãng; nó chỉ xử lý một **chuỗi hợp lệ theo format**.

Để kiểm tra phiên bản JDK thực sự được sử dụng khi chạy ứng dụng:

~~~java
// Java 10+, trong một phương thức.
Runtime.Version runtime = Runtime.version();

System.out.println(runtime.feature());
System.out.println(runtime.interim());
System.out.println(runtime.update());
System.out.println(runtime.patch());
~~~

Bốn dòng in phụ thuộc **JVM đang chạy**, nên không có stdout số cụ thể chung cho mọi máy. Bài có một chương trình Java 17+ ở mục 10, sử dụng các chuỗi phiên bản mẫu cố định để đưa ra stdout có thể kiểm chứng chính xác.

## 2. FEATURE: bộ đếm của bản phát hành tính năng

**`FEATURE`** là phần tử đầu tiên của số phiên bản và tăng mỗi khi có một **feature release**, bất kể số lượng tính năng cụ thể được bổ sung nhiều hay ít.

~~~text
17
18
19
20
21
...
~~~

Trong mô hình phát hành sáu tháng của OpenJDK:

- Các feature release thường xuất hiện vào khoảng **tháng 3** và **tháng 9**.
- Bộ đếm `FEATURE` tăng từ bản feature này sang bản feature tiếp theo.
- Một feature release có thể bổ sung API, công cụ, tính năng ngôn ngữ/JVM, hoặc những thay đổi khác theo quá trình chuẩn hóa tương ứng.
- Theo chính sách phát hành đã công bố, một feature release có thể chứa thay đổi không tương thích hoặc loại bỏ thành phần đã được thông báo theo quy trình; đừng coi mọi bước tăng FEATURE là một bản cập nhật sửa lỗi nhỏ.

Ví dụ: `17` và `21` là **hai giá trị FEATURE khác nhau**. Con số `21` không có nghĩa “phiên bản 2.1” hay “21 bản vá”. Đây là chỉ số dòng phát hành theo mô hình Java từ JDK 10.

~~~java
Runtime.Version v = Runtime.Version.parse("21.0.2");

System.out.println(v.feature()); // 21
~~~

### FEATURE khác việc ứng dụng đã tương thích

Nếu ứng dụng chạy trên JDK có `feature() == 21`, điều đó **không chứng minh** mọi thư viện, bytecode, module và cấu hình của ứng dụng đều tương thích với Java 21. Các vấn đề tương thích còn phụ thuộc:

- Cấp bytecode của file `.class` và `--release` dùng khi biên dịch.
- API của nền tảng mà code đang gọi.
- Quy tắc module, reflective access và các thay đổi hành vi.
- Thư viện/framework/native dependency đi cùng.
- Lựa chọn compiler, runtime image và các cờ JVM.

`feature()` là một **số phiên bản nền tảng**, không phải chứng chỉ tương thích tự động.

### FEATURE và LTS là hai thông tin khác nhau

Một số dòng JDK được từng nhà phân phối cung cấp **hỗ trợ dài hạn (LTS)**, nhưng `FEATURE` **không tự mã hóa** chính sách hỗ trợ hoặc hạn sử dụng của nhà phân phối. Ví dụ, ứng dụng có thể chọn một dòng LTS theo tiêu chuẩn vận hành, nhưng lịch cập nhật bảo mật, phạm vi hỗ trợ và điều kiện phân phối phải được xác minh theo **nhà cung cấp và gói sản phẩm cụ thể**.

Đừng viết logic “`feature()%4 == ...` nghĩa là luôn là LTS” hoặc giả định mọi hãng cam kết vòng đời hỗ trợ giống nhau.

## 3. INTERIM: bộ đếm dành cho phát hành trung gian

**`INTERIM`** là phần tử thứ hai. Theo JEP 322, nó được dành cho những **interim releases** có thể chứa sửa lỗi và cải tiến tương thích nhưng không thay đổi API chuẩn, không loại bỏ tính năng hay đưa vào thay đổi không tương thích theo hợp đồng của nhóm phát hành này.

Đây là **khả năng được thiết kế cho mô hình tổng quát**, chứ **không phải một chu kỳ phát hành trung gian đang diễn ra định kỳ** trong nhịp OpenJDK sáu tháng.

Trong mô hình sáu tháng đang áp dụng:

~~~text
$INTERIM = 0
~~~

Vị trí này được giữ để mô hình có thể hỗ trợ một nhịp phát hành khác nếu chính sách phát hành thay đổi. Không nhầm `INTERIM` với bản update bảo mật phát hành ba tháng một lần.

### Vì sao thấy một số 0 giữa phiên bản?

~~~text
21.0.2
   ^
   INTERIM = 0
~~~

Đây là số `0` **ở giữa**, phải giữ để phân biệt `UPDATE` là thành phần thứ ba. Nếu tự xóa nó và đổi `21.0.2` thành `21.2`, bạn đã biến `UPDATE=2` thành `INTERIM=2`. Hai số có **ý nghĩa khác nhau** và không phải cùng phiên bản.

~~~java
var update = Runtime.Version.parse("21.0.2");
var interimExample = Runtime.Version.parse("21.2");

System.out.println(update.interim()); // 0
System.out.println(update.update());  // 2

System.out.println(interimExample.interim()); // 2
System.out.println(interimExample.update());  // 0
~~~

`21.2` được dùng như **ví dụ phân tích số**, không phải khẳng định có JDK 21.2 chính thức. Đây là lý do không nên tự cắt các thành phần `0` nằm **giữa** số phiên bản.

### INTERIM không phải minor theo nghĩa cũ

Các tên phương thức `major()`, `minor()`, `security()` của `Runtime.Version` vẫn tồn tại vì tương thích với code cũ, nhưng đã được **đánh dấu deprecated từ Java 10** do ý nghĩa những vị trí phiên bản đã thay đổi.

Cách viết được Javadoc hiện hành hướng dẫn là:

~~~java
v.feature(); // Thay cho major()
v.interim(); // Thay cho minor()
v.update();  // Thay cho security()
v.patch();   // Thành phần thứ tư
~~~

Không hướng dẫn dùng `minor()` để đọc bản vá, bởi giá trị đó tương ứng INTERIM, và trong mô hình hiện tại thường bằng `0`.

## 4. UPDATE: bộ đếm các bản cập nhật tương thích

**`UPDATE`** là phần tử thứ ba. Một **update release** chủ yếu chứa những sửa chữa tương thích: lỗi bảo mật, regression hoặc bug trong các tính năng mới được phát hành.

Ví dụ trong cùng một dòng feature:

~~~text
21       -> FEATURE=21, INTERIM=0, UPDATE=0, PATCH=0
21.0.1   -> FEATURE=21, INTERIM=0, UPDATE=1, PATCH=0
21.0.2   -> FEATURE=21, INTERIM=0, UPDATE=2, PATCH=0
21.0.3   -> FEATURE=21, INTERIM=0, UPDATE=3, PATCH=0
~~~

Đây là **giá trị update counter**, không phải chỉ số ngày hay tháng. `UPDATE=3` không có nghĩa là ba lỗ hổng đã sửa hoặc rằng mọi phát hành đều chứa cùng số bản vá.

Trong nhịp phát hành JDK hiện hành, các bản update được lên lịch sau feature release khoảng một tháng và theo các đợt cập nhật hàng quý tiếp theo. **Lịch dự kiến không bảo đảm máy của bạn tự động được nâng cấp**: nhà phân phối, cơ chế cập nhật, vùng triển khai và chính sách doanh nghiệp vẫn quyết định phiên bản thực đang chạy.

~~~java
var v = Runtime.Version.parse("21.0.12");

System.out.println(v.feature()); // 21
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 12
System.out.println(v.patch());   // 0
~~~

### UPDATE không phải PATCH

Bản cập nhật theo lịch có thể chứa sửa lỗi bảo mật hoặc các lỗi tương thích khác; đó là **UPDATE**, chứ không vì có chữ “security patch” trong release note mà thành phần thứ tư `PATCH` phải tăng. Đặt đúng tên các mức phát hành giúp không nhầm **loại đợt phát hành** với **nội dung sửa lỗi**.

### UPDATE và “đã an toàn” không đồng nghĩa

Cùng FEATURE nhưng UPDATE cao hơn thường là bản mới hơn trong dòng tương ứng. Tuy nhiên chỉ dựa vào `update()` không đủ để kết luận sản phẩm có được vá mọi CVE, hỗ trợ đến thời điểm nào hoặc đã triển khai đúng bản của nhà cung cấp.

Cần kết hợp:

- Phiên bản đầy đủ (gồm FEATURE/INTERIM/UPDATE/PATCH nếu có).
- Build và thông tin nhà phân phối nếu cần phân tích khác biệt nhị phân.
- Ngày phát hành và release notes/security advisories.
- Chính sách patch deployment và số phiên bản JDK thực chạy trong môi trường sản xuất.

Nếu một tổ chức dùng nhiều JDK vendor, sự khác biệt về build và backport có thể quan trọng; tránh suy luận quá mức từ ba chữ số đầu.

## 5. PATCH: bộ đếm của bản vá khẩn cấp

**`PATCH`** là phần tử thứ tư và tăng khi cần phát hành một bản vá **khẩn cấp** để xử lý vấn đề nghiêm trọng (*emergency patch release*).

Ví dụ:

~~~text
21.0.2     -> PATCH = 0
21.0.2.1   -> PATCH = 1
~~~

Số `21.0.2.1` có ý nghĩa: dòng feature 21, không có interim, update 2, sau đó có emergency patch mức 1. Nó **không** có nghĩa phát hành một feature mới và cũng không đồng nghĩa update counter tăng thành 3.

~~~java
var regular = Runtime.Version.parse("21.0.2");
var emergency = Runtime.Version.parse("21.0.2.1");

System.out.println(regular.patch());      // 0
System.out.println(emergency.patch());    // 1
System.out.println(emergency.update());   // 2
~~~

### PATCH khác UPDATE về mục đích

| Tiêu chí | UPDATE | PATCH |
| --- | --- | --- |
| Thành phần | Thứ ba | Thứ tư |
| Loại phát hành | Bản cập nhật tương thích, thường theo lịch | Bản vá khẩn cấp khi cần |
| Nội dung điển hình | Bảo mật, regression, bug fixes | Vấn đề nghiêm trọng cần sửa ngoài chu kỳ |
| Ví dụ cấu trúc | `21.0.3` | `21.0.2.1` |
| Điều gì không được suy ra? | Không tự khẳng định không còn lỗ hổng | Không nhất thiết có mặt ở mọi chu kỳ update |

**Đừng giả định PATCH luôn bằng 0.** Dù nhiều phiên bản dùng tên ba thành phần như `21.0.12`, mô hình vẫn cho phép thành phần thứ tư khi cần. Ngược lại, không tự thêm `.0` thành phần cuối cho mọi version string.

### Khi PATCH tăng, những thành phần khác có giữ nguyên?

Trong ví dụ `21.0.2` → `21.0.2.1`, FEATURE/INTERIM/UPDATE giữ nguyên và PATCH tăng. Theo quy tắc mô hình, khi một thành phần cao hơn được tăng thì những thành phần phía sau bị loại bỏ để bắt đầu dòng phiên bản tiếp theo.

Ví dụ về **thứ tự số phiên bản**:

~~~text
21.0.2   < 21.0.2.1 < 21.0.3 < 22
~~~

Đây là quan hệ thứ tự **numeric version**. Khi so sánh bản dựng EA/GA và metadata, cần hiểu thêm các thành phần sau số phiên bản ở mục 7–8.

## 6. Số 0 được lược bỏ ở cuối, không lược số 0 ở giữa

Theo JEP 322, các thành phần số phiên bản là những số nguyên không âm hợp lệ, không có **leading zero**, và một **version number không có thành phần 0 ở cuối**.

Điều đó có hai hệ quả quan trọng.

### 6.1. Thành phần vắng ở cuối có giá trị logic bằng 0

~~~text
21             -> FEATURE=21, INTERIM=0, UPDATE=0, PATCH=0
21.0.1         -> FEATURE=21, INTERIM=0, UPDATE=1, PATCH=0
21.0.2.1       -> FEATURE=21, INTERIM=0, UPDATE=2, PATCH=1
~~~

Khi đọc bằng `Runtime.Version`:

~~~java
var onlyFeature = Runtime.Version.parse("21");
var oneUpdate = Runtime.Version.parse("21.0.1");

System.out.println(onlyFeature.interim()); // 0
System.out.println(onlyFeature.update());  // 0
System.out.println(onlyFeature.patch());   // 0

System.out.println(oneUpdate.patch());     // 0
~~~

Cặp số `21.0.1` hợp lệ vì có `0` ở giữa, còn thành phần cuối là `1`.

### 6.2. Không thêm số 0 ở cuối vào version number

Những chuỗi minh họa sau **không đúng dạng canonical của version number**:

~~~text
21.0
21.0.0
21.0.2.0
~~~

Thay thế lần lượt bằng `21`, `21` và `21.0.2`. Đừng tự suy ra rằng “đủ bốn số mới đúng”. Trên Java 17, `Runtime.Version.parse` kiểm tra cú pháp version string và có thể ném `IllegalArgumentException` với các ví dụ có trailing-zero trái định dạng này.

### 6.3. Không bỏ số 0 ở giữa

~~~text
21.0.2     -> INTERIM=0, UPDATE=2
21.2       -> INTERIM=2, UPDATE=0
~~~

Hai chuỗi có ý nghĩa và thứ tự so sánh khác nhau. Nếu xây version string bằng nối chuỗi thủ công, phải giữ đúng **vị trí** mỗi thành phần, không `split` rồi loại mọi phần tử bằng chuỗi `"0"`.

### 6.4. Có thể có thành phần thứ năm trở đi

JEP 322 cho phép phần tử thứ năm trở đi để các nhà triển khai/nền tảng sử dụng theo chính sách của họ, ví dụ bản vá đặc thù của downstream distributor. Bốn accessor chuẩn `feature()/interim()/update()/patch()` chỉ lấy **bốn vị trí đầu**; khi cần xem đầy đủ dãy số, dùng `Runtime.Version.version()`.

Không tự gán ý nghĩa quốc tế chung cho vị trí thứ năm, và không kết luận hai bản build có cùng bốn số đầu là hoàn toàn giống nhau.

## 7. Phân biệt VERSION NUMBER và VERSION STRING

Một **version number** bao gồm dãy số theo vị trí; một **version string** có thể chứa thêm thông tin khác.

Dạng tổng quan:

~~~text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
~~~

Đây là cách diễn đạt các dạng hỗ trợ của JEP 322; ký hiệu `?` là “có thể có” chứ không phải ký tự cần gõ nguyên văn. Các thành phần:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `$VNUM` | `21.0.2` | Dãy số phiên bản; bốn vị trí đầu là FEATURE/INTERIM/UPDATE/PATCH |
| `$PRE` | `ea` | Pre-release identifier, ví dụ bản early access |
| `$BUILD` | `13` | Số build |
| `$OPT` | `LTS` | Thông tin build tùy chọn do nhà triển khai cung cấp |

Ví dụ:

~~~text
21
21.0.2
21.0.2+13
21.0.2+13-LTS
21-ea+3
21.0.2.1+1
~~~

`+13` là **số build**, không phải `UPDATE=13`. `-ea` là dấu hiệu bản phát hành trước GA, không phải `INTERIM`. `-LTS` ở sau build là **thông tin build tùy chọn**, không trở thành số thứ năm của version number.

~~~java
var release = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(release.feature());  // 21
System.out.println(release.interim());  // 0
System.out.println(release.update());   // 2
System.out.println(release.patch());    // 0
System.out.println(release.build().orElse(-1)); // 13
System.out.println(release.optional().orElse("")); // LTS
~~~

### LTS là thông tin từ nhà phân phối

JEP 322 có quy ước để nhà triển khai có thể đánh dấu một dòng có hỗ trợ dài hạn bằng thông tin `$OPT` bắt đầu bằng `LTS`. Tuy nhiên, **sự có mặt/vắng mặt của chuỗi LTS trong version string không tự chứng minh mọi quyền hỗ trợ, lịch vá, điều khoản sử dụng hoặc tính tương đương của các bản phân phối**.

Để đưa ra quyết định vận hành (ví dụ phải duy trì JDK trong 24 tháng), cần tham khảo thông báo chính thức của nhà cung cấp, phạm vi sản phẩm và chính sách an ninh; không chỉ viết điều kiện tìm chữ `LTS` trong chuỗi.

### PRE khác UPDATE/PATCH

~~~java
var early = Runtime.Version.parse("21-ea+3");

System.out.println(early.feature()); // 21
System.out.println(early.pre().orElse("")); // ea
System.out.println(early.build().orElse(-1)); // 3
~~~

Giá trị `21-ea+3` không phải bản `UPDATE=3`. Dấu cộng mở phần build; chỉ thành phần thứ ba **bên trong dãy số** `$VNUM` mới là UPDATE.

## 8. Dùng Runtime.Version thay vì so sánh chuỗi

### 8.1. Đọc phiên bản JVM đang chạy

~~~java
Runtime.Version runtime = Runtime.version();

int feature = runtime.feature();
int interim = runtime.interim();
int update = runtime.update();
int patch = runtime.patch();
~~~

`Runtime.version()` trả về một đối tượng `Runtime.Version` mô tả phiên bản **runtime hiện tại**. Giá trị phụ thuộc JDK/JRE đang chạy ứng dụng; không suy từ tên file nguồn hoặc từ `--release` khi biên dịch.

Có thể dùng `java --version` trong terminal để xem runtime/VM build và thông tin phân phối tương ứng. Đầu ra là **dữ liệu thực của máy**, không nên đặt vào “stdout chính xác” của ví dụ giả định.

### 8.2. Phân tích một chuỗi bất kỳ theo format

~~~java
Runtime.Version parsed = Runtime.Version.parse("17.0.10");

System.out.println(parsed.feature()); // 17
System.out.println(parsed.interim()); // 0
System.out.println(parsed.update());  // 10
System.out.println(parsed.patch());   // 0
~~~

`parse(String)` chỉ phân tích cú pháp. Nó **không tải JDK**, không gọi website nhà phân phối và **không xác minh một gói phát hành có thật hay đang được hỗ trợ**.

### 8.3. Không so sánh lexicographic

Chuỗi:

~~~text
"21.0.10"
"21.0.9"
~~~

Nếu so bằng `String.compareTo`, chữ `'1'` của `10` có thể được coi nhỏ hơn chữ `'9'`, dẫn tới thứ tự sai về mặt version number.

~~~java
String a = "21.0.10";
String b = "21.0.9";

System.out.println(a.compareTo(b) > 0); // false — sai về thứ tự version
System.out.println(
        Runtime.Version.parse(a)
                .compareTo(Runtime.Version.parse(b)) > 0
); // true — đúng theo các thành phần số
~~~

`Runtime.Version.compareTo` so các thành phần phiên bản theo quy tắc JDK. Không dùng các phép so chuỗi thủ công nếu cần phân loại phiên bản chính xác.

### 8.4. Thứ tự trong cùng một dòng FEATURE

~~~java
var base = Runtime.Version.parse("21.0.2");
var emergency = Runtime.Version.parse("21.0.2.1");
var nextUpdate = Runtime.Version.parse("21.0.3");
var nextFeature = Runtime.Version.parse("22");

System.out.println(emergency.compareTo(base) > 0);        // true
System.out.println(nextUpdate.compareTo(emergency) > 0); // true
System.out.println(nextFeature.compareTo(nextUpdate) > 0); // true
~~~

Đừng cắt chuỗi thành hai đoạn rồi so `UPDATE` riêng lẻ. Một phiên bản ở FEATURE mới có thể có UPDATE bằng 0 mà vẫn mới hơn một phiên bản ở FEATURE cũ với UPDATE lớn.

### 8.5. Pre-release, build và optional metadata

`Runtime.Version` có:

~~~java
v.pre();      // Optional<String>
v.build();    // Optional<Integer>
v.optional(); // Optional<String>
~~~

Khi so sánh hai version strings, `compareTo` xử lý cả thông tin phù hợp theo quy tắc API. Nếu muốn **bỏ qua riêng phần thông tin tùy chọn `$OPT`**, dùng `compareToIgnoreOptional` hoặc `equalsIgnoreOptional` thay vì tự xóa ký tự cuối chuỗi.

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13");

System.out.println(a.equalsIgnoreOptional(b)); // true
System.out.println(a.compareToIgnoreOptional(b) == 0); // true
~~~

**Lưu ý:** `IgnoreOptional` không có nghĩa “bỏ qua mọi thứ sau dấu +” hoặc “chỉ so FEATURE”. Nó bỏ qua **optional build information**, nhưng pre-release và build number vẫn có quy tắc riêng. Đọc Javadoc khi kiểm tra một chính sách so sánh phức tạp.

## 9. Ví dụ quyết định phiên bản trong ứng dụng

### 9.1. Kiểm yêu cầu tối thiểu về FEATURE

Nếu một ứng dụng cần **API được bổ sung từ Java 17**, có thể kiểm tra runtime:

~~~java
if (Runtime.version().feature() < 17) {
    throw new IllegalStateException(
            "This program requires Java 17 or newer");
}
~~~

Đoạn mã này phù hợp khi yêu cầu nghiệp vụ là **không thấp hơn Java 17 về mức feature**. Tuy nhiên nó không thay cho kiểm bytecode: nếu class đã biên dịch bằng target Java 17, một JVM quá cũ có thể từ chối nạp class bằng `UnsupportedClassVersionError` **trước khi** chạy tới câu `if`.

### 9.2. Đặt điều kiện cho một mức cập nhật cụ thể

Giả sử nhà phân phối đưa ra khuyến nghị bảo mật trên dòng Java 21 và cần so với `21.0.12`:

~~~java
Runtime.Version installed = Runtime.version();
Runtime.Version minimum = Runtime.Version.parse("21.0.12");

if (installed.feature() == 21
        && installed.compareTo(minimum) < 0) {
    System.err.println("Java 21 runtime is below the target update");
}
~~~

Đoạn này **chỉ minh họa cách so sánh**, không phải một thông báo rằng `21.0.12` là mức tối thiểu bảo mật hiện tại. Trước khi đặt ngưỡng, cần xác định patch, build, vendor và thời điểm theo advisories thật.

**Không** đặt điều kiện đơn giản `installed.update() < 12` cho **mọi FEATURE**: một JDK feature mới có `update()==0`, nhưng không vì thế bị xem là cũ hơn toàn bộ JDK dòng 21.

### 9.3. Ghi thông tin môi trường vào log

~~~java
Runtime.Version version = Runtime.version();

System.out.println("JDK version: " + version);
System.out.println("Feature level: " + version.feature());
~~~

Khi cần phân tích sự cố, còn có thể ghi giá trị từ `System.getProperty("java.vendor")`, `System.getProperty("java.vendor.version")`, `System.getProperty("java.version.date")` nếu môi trường cung cấp, và kết quả `java --version`. Đừng log thông tin cấu hình nhạy cảm không liên quan.

`java.version.date` là thuộc tính do JEP 322 bổ sung giúp nhận biết ngày GA dự kiến/thực tế của bản phát hành. Nó khác `UPDATE` và không nên được biến thành một phần tử số phiên bản thứ năm.

### 9.4. Java source/target khác Runtime.Version

Ba điều độc lập:

- **Ngôn ngữ**: cú pháp nguồn được compiler hỗ trợ.
- **Bytecode**: cấp class-file được JVM hỗ trợ.
- **Runtime API và bản vá**: phiên bản runtime thật đang thực thi.

~~~bash
# Ví dụ dùng một JDK mới để biên dịch chương trình nhắm Java 17:
javac --release 17 MyApp.java

# Xem runtime được chọn bởi PATH/JAVA_HOME khi chạy:
java --version
~~~

`--release 17` giới hạn API/cú pháp/target theo Java 17, nhưng **không tự cài bản cập nhật bảo mật Java 17 mới nhất** trên máy chạy. Các công cụ `javac` và `java` trên PATH cũng có thể trỏ tới hai JDK khác nhau; hãy xác nhận môi trường build và deployment.

## 10. Chương trình Java 17+ hoàn chỉnh, có stdout chính xác

File này phân tích một tập hợp **version strings cố định**, do đó kết quả không phụ thuộc JDK mới nhất hay nhà phân phối đang cài. Chỉ dòng cuối kiểm mức feature của runtime bằng điều kiện `>= 17` khi chạy đúng yêu cầu.

Lưu file đúng tên **`JavaVersionComponentsDemo.java`**:

~~~java
import java.util.List;

public class JavaVersionComponentsDemo {

    static String components(Runtime.Version version) {
        return version.feature() + "."
                + version.interim() + "."
                + version.update() + "."
                + version.patch();
    }

    public static void main(String[] args) {
        Runtime.Version featureOnly =
                Runtime.Version.parse("21");
        Runtime.Version updated =
                Runtime.Version.parse("21.0.2");
        Runtime.Version emergency =
                Runtime.Version.parse("21.0.2.1");

        System.out.println("featureOnly="
                + components(featureOnly));
        System.out.println("updated="
                + components(updated));
        System.out.println("emergency="
                + components(emergency));

        System.out.println("updateParts="
                + updated.version());
        System.out.println("omittedAreZero="
                + (featureOnly.interim() == 0
                        && featureOnly.update() == 0
                        && featureOnly.patch() == 0));

        Runtime.Version conceptualInterim =
                Runtime.Version.parse("21.2");
        System.out.println("interimExample="
                + components(conceptualInterim));
        System.out.println("updateNotInterim="
                + (updated.update() == 2
                        && updated.interim() == 0));

        Runtime.Version nextUpdate =
                Runtime.Version.parse("21.0.3");
        Runtime.Version nextFeature =
                Runtime.Version.parse("22");

        System.out.println("patchNewerThanUpdate="
                + (emergency.compareTo(updated) > 0));
        System.out.println("nextUpdateNewerThanPatch="
                + (nextUpdate.compareTo(emergency) > 0));
        System.out.println("nextFeatureNewer="
                + (nextFeature.compareTo(nextUpdate) > 0));

        String textA = "21.0.10";
        String textB = "21.0.9";

        System.out.println("lexicalSaysNewer="
                + (textA.compareTo(textB) > 0));
        System.out.println("numericSaysNewer="
                + (Runtime.Version.parse(textA).compareTo(
                        Runtime.Version.parse(textB)) > 0));

        Runtime.Version withOptional =
                Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version withoutOptional =
                Runtime.Version.parse("21.0.2+13");

        System.out.println("build="
                + withOptional.build().orElse(-1));
        System.out.println("optional="
                + withOptional.optional().orElse(""));
        System.out.println("sameIgnoringOptional="
                + withOptional.equalsIgnoreOptional(
                        withoutOptional));
        System.out.println("compareIgnoringOptional="
                + (withOptional.compareToIgnoreOptional(
                        withoutOptional) == 0));

        Runtime.Version earlyAccess =
                Runtime.Version.parse("21-ea+3");
        System.out.println("preRelease="
                + earlyAccess.pre().orElse(""));
        System.out.println("preBuild="
                + earlyAccess.build().orElse(-1));

        boolean trailingZeroRejected = false;
        try {
            Runtime.Version.parse("21.0.2.0");
        } catch (IllegalArgumentException expected) {
            trailingZeroRejected = true;
        }
        System.out.println("trailingZeroRejected="
                + trailingZeroRejected);

        System.out.println("runtimeAtLeast17="
                + (Runtime.version().feature() >= 17));
    }
}
~~~

Lệnh biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 JavaVersionComponentsDemo.java
java JavaVersionComponentsDemo
~~~

**Stdout chính xác trên JDK 17+ theo hợp đồng Runtime.Version:**

~~~text
featureOnly=21.0.0.0
updated=21.0.2.0
emergency=21.0.2.1
updateParts=[21, 0, 2]
omittedAreZero=true
interimExample=21.2.0.0
updateNotInterim=true
patchNewerThanUpdate=true
nextUpdateNewerThanPatch=true
nextFeatureNewer=true
lexicalSaysNewer=false
numericSaysNewer=true
build=13
optional=LTS
sameIgnoringOptional=true
compareIgnoringOptional=true
preRelease=ea
preBuild=3
trailingZeroRejected=true
runtimeAtLeast17=true
~~~

### Giải thích đầu ra

1. Hàm `components` **chủ động in đủ bốn vị trí** để dễ học, nên `21` được hiển thị là `21.0.0.0` **trong output bài demo**. Đó không phải chuỗi version canonical cần đem dùng để parse hay công bố; version number chuẩn vẫn lược các số `0` ở cuối.
2. `updated.version()` trả danh sách các thành phần số **được ghi trực tiếp** trong version number: `[21,0,2]`, không tự nối thành bốn phần tử chỉ vì có bốn accessor.
3. `interimExample=21.2.0.0` biểu diễn cách các accessor đọc `21.2`: INTERIM=2, UPDATE=0. Đây là **ví dụ cú pháp**, không phải thông báo về một phát hành thực tế.
4. `emergency` mới hơn `updated` theo thứ tự số, và `21.0.3` mới hơn `21.0.2.1`. `22` là FEATURE lớn hơn các version thuộc dòng `21`.
5. So sánh chuỗi `21.0.10` với `21.0.9` bằng `String.compareTo` cho kết luận sai về số phiên bản; `Runtime.Version.compareTo` xử lý đúng vị trí số nguyên.
6. `+13` được đọc bằng `build()`; `LTS` được đọc bằng `optional()`; `equalsIgnoreOptional` và `compareToIgnoreOptional` coi hai chuỗi có cùng số version và build là tương đương khi bỏ qua metadata tùy chọn.
7. `21-ea+3` cho `preRelease=ea` và `preBuild=3`; số 3 ở đây **không** phải UPDATE.
8. Chuỗi `21.0.2.0` có trailing zero không hợp lệ với quy tắc version number, nên `Runtime.Version.parse` ném `IllegalArgumentException`.
9. Dòng `runtimeAtLeast17=true` chỉ được bảo đảm **khi làm đúng yêu cầu chạy bằng JDK 17+**. Trên máy thật, `Runtime.version()` trả version của JVM đang chạy, không phải `21` trong chuỗi mẫu.

## 11. Lỗi phổ biến khi đọc version string

| Nhận định hoặc cách làm sai | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “`21.0.2` có minor=2.” | Thành phần thứ ba là UPDATE, còn INTERIM=0 | Đọc `feature/interim/update/patch` |
| “`INTERIM` là quý tiếp theo.” | Không có chu kỳ interim thường kỳ trong mô hình sáu tháng | Hiểu INTERIM là bộ đếm dự phòng cho phát hành trung gian |
| “`UPDATE` là hotfix ngoài lịch.” | UPDATE thường là đợt cập nhật tương thích; PATCH dành cho emergency | Phân biệt mục đích từng vị trí |
| “`PATCH` có từ Java 10 nhưng không được dùng nữa.” | JEP 322 vẫn có PATCH cho emergency release | Vẫn parse/read `patch()` |
| “`21` phải được viết thành `21.0.0.0`.” | Không có trailing zero trong version number canonical | Dùng `21` |
| “Có thể bỏ mọi số 0.” | Xóa số 0 ở giữa làm thay đổi vị trí thành phần | Giữ `21.0.2`, không đổi thành `21.2` |
| “`+13` nghĩa là update 13.” | `+BUILD` là metadata build, không thuộc $VNUM | Đọc `build()` riêng |
| “`-ea` nghĩa là interim release.” | `PRE` là pre-release label, không phải INTERIM | Đọc `pre()` riêng |
| “`-LTS` chắc chắn được hỗ trợ đến một ngày nhất định.” | Metadata từ vendor không thay thế hợp đồng hỗ trợ | Đọc lịch và điều khoản của nhà cung cấp |
| “`major()/minor()/security()` là tên chuẩn nên dùng cho Java hiện đại.” | Các tên đã deprecated từ Java 10 | Ưu tiên `feature()/interim()/update()` |
| “So hai version bằng `String.compareTo` là đủ.” | Từng ký tự không biểu diễn so sánh numeric component | Dùng `Runtime.Version.compareTo` |
| “`parse` chỉ nhận những bản JDK từng phát hành.” | Parser kiểm cú pháp, không kết nối release registry | Tách parse hợp lệ với xác minh phát hành |
| “Update cao hơn luôn là bản mới hơn trên mọi FEATURE.” | Cần so FEATURE trước | So cả `Runtime.Version` |
| “JDK cài có FEATURE mới thì đã được vá mọi CVE.” | Patch trạng thái phụ thuộc full version/build/vendor | Kiểm advisories và bản thực được triển khai |
| “`--release 17` khiến runtime tự thành Java 17.” | Flag biên dịch không đổi JVM khi chạy | Kiểm riêng `java --version` và `Runtime.version()` |
| “Dùng dấu `.0` ở cuối để chuẩn hóa output rồi parse lại.” | Trailing zero là dạng không chuẩn | Giữ `toString()` gốc hoặc format theo mục đích hiển thị |

### Không đọc `java.version` bằng thao tác tách chuỗi thô khi có API sẵn

~~~java
// Không dùng một parser tự chế dựa vào index/split tùy tiện:
String versionText = System.getProperty("java.version");

// Với JDK 10+, nên dùng trực tiếp:
Runtime.Version version = Runtime.version();
~~~

`System.getProperty("java.version")` vẫn có ích để hiển thị/chẩn đoán, nhưng nếu mục tiêu là lấy đúng các thành phần version mới, `Runtime.version()` có accessor có nghĩa rõ ràng. Với **chuỗi version từ nơi khác** tuân theo format JDK, dùng `Runtime.Version.parse` và xử lý `IllegalArgumentException` nếu nguồn không hợp lệ.

Không tự áp parser này lên một phiên bản **thư viện tùy ý**: không phải mọi sản phẩm hoặc dependency tuân theo format JDK `FEATURE.INTERIM.UPDATE.PATCH`.

## 12. Checklist triển khai và kiểm thử

### Khi kiểm tra JVM đang chạy

1. Gọi `Runtime.version()` để có đối tượng mô tả runtime thực.
2. Đọc `feature()` để xác định dòng Java; không dùng tên cũ `major()` trong code mới.
3. Đọc `interim()`, `update()`, `patch()` khi cần mức bản sửa chính xác.
4. Nếu cần phân biệt build hoặc pre-release, đọc `build()`, `pre()`, `optional()`.
5. Giữ thông tin JDK vendor và release date thích hợp cho chẩn đoán, đặc biệt khi có nhiều bản phân phối.
6. Không đánh đồng version với bảo đảm về hỗ trợ LTS, binary compatibility hoặc trạng thái an ninh.
7. Nếu đặt minimum supported version, so toàn bộ thành phần hợp lý bằng `compareTo`, không so chuỗi.
8. Kiểm xem phiên bản Java ở container, máy build và máy production có thật sự là phiên bản mong muốn.

### Khi phân tích một chuỗi do người dùng/đối tác cung cấp

1. Xác định đó có phải **JDK version string** theo JEP 322 không.
2. Không bỏ `0` ở giữa, không tự thêm `0` ở cuối.
3. Gọi `Runtime.Version.parse(text)` trong một khối xử lý input không hợp lệ.
4. Phân biệt `$VNUM` và `$PRE` / `$BUILD` / `$OPT`.
5. Đừng kết luận một phiên bản parse được chắc chắn là một bản phát hành tồn tại.
6. Xác định chính sách xử lý pre-release và metadata optional khi so sánh.
7. Không đưa thông tin metadata/vendor thành các số UPDATE/PATCH.
8. Viết test trường hợp `21.0.9`, `21.0.10` và `21.0.2.1` để bắt lỗi so sánh chuỗi.

### Bài tập tự đánh giá

**Câu 1.** `21.0.2` có FEATURE, INTERIM, UPDATE và PATCH lần lượt bằng bao nhiêu?

**Đáp án:** `21, 0, 2, 0`. PATCH vắng mặt trong string nhưng accessor trả `0`.

**Câu 2.** `21.2` có giống `21.0.2` không?

**Đáp án:** Không. `21.2` có INTERIM=2 và UPDATE=0; `21.0.2` có INTERIM=0 và UPDATE=2.

**Câu 3.** Trong mô hình phát hành JDK sáu tháng, INTERIM thường có giá trị nào?

**Đáp án:** `0`. Vị trí được giữ cho những mô hình có interim releases, không phải bộ đếm bản update hàng quý.

**Câu 4.** `21.0.2.1` biểu diễn điều gì?

**Đáp án:** FEATURE 21, INTERIM 0, UPDATE 2, PATCH 1; PATCH dùng cho một đợt vá khẩn cấp.

**Câu 5.** Tại sao không viết `21.0.2.0` để luôn có bốn số?

**Đáp án:** Version number chuẩn không cho thành phần `0` ở cuối. Dạng canonical của nó là `21.0.2`.

**Câu 6.** `21.0.2+13-LTS` có UPDATE=13 không?

**Đáp án:** Không. UPDATE=2; build=13; `LTS` là metadata tùy chọn.

**Câu 7.** `21-ea+3` có PATCH hoặc UPDATE bằng 3 không?

**Đáp án:** Không. FEATURE=21, INTERIM/UPDATE/PATCH=0; `ea` là pre-release identifier và `3` là build number.

**Câu 8.** Vì sao `"21.0.10".compareTo("21.0.9")` không phù hợp?

**Đáp án:** Vì so ký tự theo từ điển không phải so các thành phần số nguyên. Dùng `Runtime.Version.parse(...).compareTo(...)`.

**Câu 9.** `Runtime.Version.parse("21.2")` có chứng minh JDK 21.2 từng phát hành không?

**Đáp án:** Không. `parse` chỉ xác nhận và xử lý format version, không kiểm tra lịch sử phát hành.

**Câu 10.** Nên gọi `major()` hay `feature()` cho code mới từ Java 10 trở lên?

**Đáp án:** `feature()`, vì `major()` đã deprecated và có tên không phản ánh đúng mô hình phát hành theo thời gian.

**Câu 11.** Nếu `Runtime.version().feature()` trả `21`, có đủ kết luận runtime đã được cập nhật bảo mật không?

**Đáp án:** Không. Cần biết UPDATE/PATCH, build, vendor, release notes và lịch hỗ trợ theo bản triển khai.

**Câu 12.** PATCH có phải “mọi lần sửa lỗi đều làm PATCH tăng” không?

**Đáp án:** Không. Bản UPDATE thường chứa những sửa lỗi và bảo mật định kỳ; PATCH theo mô hình là emergency patch release cho vấn đề nghiêm trọng.

## 13. Tài liệu chuẩn còn áp dụng hiện nay

- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): tài liệu thiết kế chính thức từ Java 10, định nghĩa FEATURE/INTERIM/UPDATE/PATCH, quy tắc số 0, pre-release/build/optional và thay đổi API `Runtime.Version`.
- [Oracle Java SE 26 — Runtime.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): đặc tả hiện đại cho `feature()`, `interim()`, `update()`, `patch()`, `parse`, `version`, `compareTo`, `build`, `pre`, `optional` và các phương thức cũ đã deprecated.
- [Oracle Java SE 17 — Runtime.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): hợp đồng API đúng target của chương trình minh họa Java 17+.
- [Oracle Java SE 25 — JDK Installation Guide, Version-String Format](https://docs.oracle.com/en/java/javase/25/install/version-string-format.html): giải thích nhịp feature release, INTERIM=0, update định kỳ, patch khẩn cấp và quy tắc không có trailing zero.
- [Oracle Java SE 17 — Version-String Format](https://docs.oracle.com/en/java/javase/17/install/version-string-format.html): mô hình bốn thành phần còn được áp dụng trên dòng Java 17.
- [Oracle Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#version()): API lấy version của JVM hiện đang chạy.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `--version` và `-version` để xem JVM được dùng khi thực thi.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): giải thích `--release` để biên dịch với API và target của Java được chỉ định.

**Kết luận:** trong Java 10+ theo JEP 322, **FEATURE** đếm bản phát hành tính năng, **INTERIM** dành cho phát hành trung gian (hiện bằng 0 trong nhịp sáu tháng), **UPDATE** đếm bản cập nhật tương thích, và **PATCH** đếm bản vá khẩn cấp. Các số `0` cuối chuỗi được lược bỏ nhưng số `0` ở giữa phải giữ để định vị chính xác UPDATE/PATCH. Dùng `Runtime.Version` thay cho parser hoặc phép so chuỗi tự viết; đồng thời phân biệt version number với `$PRE`, `$BUILD` và `$OPT` khi phân tích JDK thực tế.