# Xử lý IllegalArgumentException khi chuỗi phiên bản Runtime.Version không hợp lệ

> **Java 10 — Runtime.Version.** Bài hướng dẫn cách xử lý đầu vào không hợp lệ khi gọi `Runtime.Version.parse(String)` theo mô hình chuỗi phiên bản JDK hiện đại (JEP 322), phân biệt **`IllegalArgumentException`**, **`NumberFormatException`** và **`NullPointerException`**, sau đó biến chúng thành thông báo lỗi rõ ràng tại ranh giới cấu hình hoặc API. Phương thức `Runtime.Version.parse` có từ Java 9 và tiếp tục được dùng trên JDK hiện đại; Java 10 chuẩn hóa ý nghĩa `FEATURE.INTERIM.UPDATE.PATCH`. Chỉ sử dụng cách làm còn phù hợp các JDK được hỗ trợ, không dựa vào các quy tắc phiên bản Java cũ đã legacy.

## 1. Mục tiêu

Hoàn thành bài này, bạn cần biết:

1. Đọc đúng hợp đồng `Runtime.Version.parse(String)` và ba nhóm ngoại lệ có thể phát sinh.
2. Xác định chuỗi phiên bản **hợp lệ về cú pháp** và phân biệt nó với “bản JDK thực sự tồn tại/được hỗ trợ/bảo mật”.
3. Nhận diện lỗi: chuỗi rỗng, số 0 ở cuối, số có leading zero, thiếu thành phần, dấu `+`/`-` sai vị trí, text banner và phần số vượt miền `Integer`.
4. Hiểu **`NumberFormatException extends IllegalArgumentException`**, nên chỉ cần bắt `IllegalArgumentException` nếu muốn gộp các lỗi parse; nếu cần phân loại, phải bắt subclass trước.
5. Hiểu `null` ném **`NullPointerException`**, không mặc nhiên bị catch `IllegalArgumentException` bắt.
6. Viết API validation **không đánh tráo giá trị**: tự chọn xử lý null, blank, khoảng trắng, malformed, overflow, logging và lỗi trả về.
7. Biết không nên dùng `String.compareTo` hoặc tách chuỗi tùy tiện thay cho `Runtime.Version`.
8. Xây dựng test dương và test âm có kết quả ổn định, không phụ thuộc vào JDK đang cài, vendor, ngày phát hành hoặc thông báo exception.
9. Chạy được chương trình Java 17+ độc lập với **27 dòng stdout** minh họa các nhánh hợp lệ và lỗi.

## 2. Nền tảng: JEP 322 và Runtime.Version

### 2.1. Vì sao Java 10 cần mô hình phiên bản mới?

Java 10 áp dụng **JEP 322 — Time-Based Release Versioning**, dùng các thành phần số chính:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

- `FEATURE`: bộ đếm phát hành tính năng.
- `INTERIM`: bộ đếm phát hành trung gian tương thích, nếu mô hình có dùng.
- `UPDATE`: bộ đếm bản cập nhật khắc phục lỗi, bảo mật và hồi quy.
- `PATCH`: bộ đếm bản vá khẩn cấp cho vấn đề nghiêm trọng.

Các thành phần ở vị trí thứ năm trở đi có thể do downstream implementor sử dụng. Một chuỗi phiên bản hợp lệ **không buộc phải hiển thị đủ bốn thành phần**: ví dụ `21` và `21.0.2` hợp lệ, trong khi `21.0.0` không hợp lệ do có thành phần 0 ở cuối.

`Runtime.Version` tồn tại từ Java 9; các accessor `feature()`, `interim()`, `update()`, `patch()` được bổ sung từ Java 10 để diễn đạt mô hình JEP 322. Không nên tiếp tục giới thiệu `major()`, `minor()`, `security()` đã deprecated trong mã mới.

### 2.2. Cấu trúc VNUM và VSTR

**`$VNUM`** là phần số phiên bản. Dạng chính thức được JEP 322 trình bày bằng biểu thức:

```regex
[1-9][0-9]*((\.0)*\.[1-9][0-9]*)*
```

Ý nghĩa:
- Thành phần đầu **dương**, không có leading zero.
- Các thành phần ở giữa có thể bằng 0.
- Thành phần **cuối** phải khác 0.
- Không có thành phần rỗng giữa hai dấu chấm.
- Mỗi phần số và số build phải vừa giới hạn `Integer` của Java khi parser trả về các giá trị `int`.

**`$VSTR`** là chuỗi phiên bản đầy đủ, gồm VNUM và tùy chọn `PRE`, `BUILD`, `OPT`:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
```

Trong đó:
- `$PRE`: ký hiệu pre-release, ví dụ `ea` hoặc `internal`.
- `$BUILD`: số build; không được có leading zero, ngoại trừ chính số `0`.
- `$OPT`: phần mô tả bổ sung, ví dụ `LTS`.
- Dấu `-` trước `PRE` và dấu `-` trước `OPT` **không có cùng nghĩa**; vị trí dấu `+` quyết định cách hiểu.

Ví dụ:
- `21`: chỉ có VNUM.
- `21.0.2`: VNUM có FEATURE=21, INTERIM=0, UPDATE=2.
- `21.0.2.1`: thêm PATCH=1.
- `21-ea+28`: PRE=ea, BUILD=28.
- `21.0.2+13-LTS`: BUILD=13 và OPT=LTS.
- `21+-LTS`: có OPT=LTS nhưng không có BUILD.

Những ví dụ trên thể hiện **chuỗi có thể parse**, không đồng nghĩa rằng nhà cung cấp đã phát hành tất cả các bản build đó trên thị trường.

### 2.3. Tại sao không tự viết parser bằng split?

Nếu chỉ làm:

```java
// MÃ MINH HỌA SAI — không dùng làm parser phiên bản.
String[] parts = input.split("\\.");
int feature = Integer.parseInt(parts[0]);
```

bạn mới lấy được một phần FEATURE trong trường hợp đơn giản. Cách này không tự xử lý `21-ea+28`, `21.0.2+13-LTS`, số 0 cuối, leading zero, cú pháp PRE/OPT hoặc quy tắc so sánh của Java. Thậm chí `split` mặc định có cách xử lý các phần rỗng ở cuối không phù hợp để xác thực toàn chuỗi.

**Giải pháp đúng cho chuỗi phiên bản Java** là `Runtime.Version.parse(input)` và kiểm tra exception được tài liệu hóa. Regex có thể hữu ích để giải thích, nhưng không nên tự thay thế parser chuẩn trong ứng dụng.

## 3. Hợp đồng exception của Runtime.Version.parse

Chữ ký:

```java
public static Runtime.Version parse(String s)
```

Javadoc Java SE hiện hành liệt kê ba nhóm lỗi:

| Tình huống | Exception | Điều cần hiểu |
| --- | --- | --- |
| Chuỗi không thể diễn giải thành phiên bản hợp lệ | `IllegalArgumentException` | Ví dụ `21.0.0`, `021`, `21..2`, `21.0.2+03` |
| Thành phần số hoặc BUILD quá lớn để biểu diễn trong `Integer` | `NumberFormatException` | **Là subclass của `IllegalArgumentException`**; có thể bắt riêng nếu cần thông báo “số quá lớn” |
| Truyền `null` | `NullPointerException` | **Không phải** subclass của `IllegalArgumentException`; phải xử lý riêng hoặc kiểm tra trước lời gọi |

Phân cấp thực tế:

```text
RuntimeException
├── IllegalArgumentException
│   └── NumberFormatException
└── NullPointerException
```

Do vậy:

```java
try {
    Runtime.Version version = Runtime.Version.parse(raw);
} catch (IllegalArgumentException ex) {
    // Bao gồm cả NumberFormatException.
}
```

Đây là **đoạn minh họa trong phương thức có biến `raw`**, không phải một chương trình độc lập. Nó **không** bắt được trường hợp `raw == null` qua nhánh `IllegalArgumentException`.

### 3.1. Khi muốn phân biệt NUMBER_OUT_OF_RANGE

```java
try {
    Runtime.Version v = Runtime.Version.parse(raw);
} catch (NumberFormatException ex) {
    // Thành phần số hoặc build number quá lớn.
} catch (IllegalArgumentException ex) {
    // Chuỗi phiên bản sai cú pháp.
}
```

Phải đặt `catch (NumberFormatException)` **trước** `catch (IllegalArgumentException)`. Nếu đặt `IllegalArgumentException` trước, nhánh subclass phía sau sẽ **unreachable**, chương trình không biên dịch.

Khi chỉ cần biết chuỗi có parse được hay không, một nhánh `catch(IllegalArgumentException)` là đủ cho cả hai nhóm; nhưng cần xử lý `null` theo chính sách rõ ràng.

### 3.2. Không bắt chung Exception rồi im lặng

Ví dụ phản mẫu:

```java
try {
    return Runtime.Version.parse(raw);
} catch (Exception ex) {
    return Runtime.version();
}
```

Đoạn này nằm trong một phương thức trả về `Runtime.Version` và có biến `raw`. Đây là **cách làm nguy hiểm** nếu cấu hình phiên bản JDK tối thiểu phải chính xác. Input `"021"` có lỗi nhưng được thay âm thầm bằng phiên bản JVM đang chạy, khiến ứng dụng **đánh mất yêu cầu gốc**.

Một fallback chỉ hợp lệ khi sản phẩm **quy định rõ**: chẳng hạn trường hiển thị tùy chọn không có giá trị thì dùng runtime hiện tại. Với validation cấu hình build, kiểm soát runtime hoặc kiểm kê bản vá, thường nên **reject** và hiển thị input/lỗi tương ứng.

### 3.3. Không phụ thuộc message của exception

Đừng viết:

```java
if (ex.getMessage().contains("Invalid version string")) {
    // ...
}
```

Thông điệp cụ thể không phải dữ liệu cấu trúc được API cam kết ổn định qua mọi bản JDK, ngôn ngữ hoặc implementation. Test nên dựa trên **loại exception** và **điều kiện input**.

Nếu ứng dụng cần đưa ra mã lỗi có cấu trúc, chính nó phải định nghĩa `INVALID_VERSION_SYNTAX`, `NUMBER_OUT_OF_RANGE`, `NULL_INPUT`... và trả mã đó một cách ổn định.

## 4. Các chuỗi sai cú pháp thường gặp

### 4.1. Bảng kiểm thử dương và âm

| Input | Parser có chấp nhận? | Lý do |
| --- | --- | --- |
| `21` | Có | VNUM chỉ có FEATURE |
| `21.0.2` | Có | 0 ở giữa hợp lệ |
| `21.0.2.1` | Có | PATCH=1 |
| `21.0.2+13-LTS` | Có | BUILD=13, OPT=LTS |
| `21-ea+28` | Có | PRE=ea, BUILD=28 |
| `21+-LTS` | Có | OPT=LTS, không có BUILD |
| `21.0` | Không | Thành phần 0 **cuối cùng** |
| `21.0.0` | Không | Thành phần 0 cuối cùng |
| `21.0.2.0` | Không | PATCH 0 ở cuối cần bỏ |
| `021` | Không | Số FEATURE có leading zero |
| `21.00.2` | Không | Số 0 phải viết `0`, không viết `00` |
| `0` | Không | FEATURE phải dương |
| `21..2` | Không | Thành phần số rỗng |
| `21.0.2+03` | Không | BUILD có leading zero |
| `21.0.2+` | Không | Dấu cộng không có nội dung build/optional hợp lệ |
| `openjdk version 21` | Không | Banner mô tả, không phải một `$VSTR` |
| `""` | Không | Chuỗi rỗng |
| `null` (tham chiếu) | Không | `NullPointerException` |
| `2147483648` | Không | FEATURE vượt `Integer.MAX_VALUE` |
| `21+2147483648` | Không | BUILD vượt `Integer.MAX_VALUE` |

Bảng này nói về **tính hợp lệ của chuỗi theo grammar Java**, không kiểm tra bản JDK có thật. `Runtime.Version.parse("99")` có thể thành công trong khi trên máy không có JDK 99. Cách kiểm tra một bộ JDK được cài thực tế là dùng nguồn metadata/runtime thích hợp, không phải chỉ chạy parse.

### 4.2. Số 0 ở giữa và ở cuối

So sánh:

```text
21          ✓ hợp lệ
21.0.2      ✓ hợp lệ
21.0.2.1    ✓ hợp lệ

21.0       ✗ sai: phần cuối bằng 0
21.0.0     ✗ sai: phần cuối bằng 0
21.0.2.0   ✗ sai: phần cuối bằng 0
```

Nguyên tắc của JEP 322: **không có thành phần 0 không cần thiết ở cuối VNUM**. Số 0 ở giữa phải được giữ nếu cần diễn đạt UPDATE hoặc PATCH về phía sau. Đừng tự động chuẩn hóa mọi input bị từ chối bằng cách xóa số 0: có thể che lỗi dữ liệu hoặc biến yêu cầu của người dùng thành một version khác.

### 4.3. Leading zero

`021`, `21.00.2`, `21.0.2+03` đều không hợp lệ theo định dạng này. Nguyên nhân:
- Thành phần dương không có `0` thừa ở đầu.
- Thành phần 0 viết đúng một chữ số `0`.
- Số BUILD không có leading zero.

**Không** dùng `Integer.parseInt` để chấp nhận `"021"` rồi lưu số 21. Mục tiêu `Runtime.Version.parse` là **xác thực và diễn giải chuỗi phiên bản hợp lệ**, không chỉ biến một phần chữ số thành số nguyên.

### 4.4. Vị trí dấu phân tách

Trong chuỗi phiên bản:
- Dấu `.` ngăn các thành phần của `$VNUM`.
- Dấu `-` có thể giới thiệu `$PRE` hoặc `$OPT` tùy ngữ cảnh.
- Dấu `+` thường giới thiệu `$BUILD` hoặc vùng `+-$OPT`.

Ví dụ `21.0.2+13` có **số BUILD 13**, còn `21.0.2.13` có **số PATCH 13**. Cùng chứa các chữ số nhưng nghĩa khác nhau.

Chuỗi `21.0.2+` thiếu BUILD/OPT hợp lệ và bị từ chối. Ngược lại `21+-LTS` có cấu trúc **`+-$OPT`** hợp lệ. Đừng kết luận “mọi `+` đều bắt buộc theo sau bằng chữ số”, bởi Javadoc có dạng đặc biệt `+-$OPT`.

## 5. Số quá lớn: NumberFormatException không phải lỗi cú pháp thông thường

Java `int` có miền tối đa `2_147_483_647`. `Runtime.Version` biểu diễn từng thành phần số và BUILD bằng `Integer`. Input như:

```text
2147483648
21+2147483648
```

không thể lưu các thành phần tương ứng trong `Integer`. Theo Javadoc, `parse` ném `NumberFormatException`. Đây là **loại con của `IllegalArgumentException`**, nên các code sau có hành vi khác nhau:

```java
try {
    Runtime.Version.parse("2147483648");
} catch (NumberFormatException ex) {
    System.out.println("NUMBER_OUT_OF_RANGE");
}
```

```java
try {
    Runtime.Version.parse("2147483648");
} catch (IllegalArgumentException ex) {
    System.out.println("INVALID_VERSION"); // Bắt cả NumberFormatException
}
```

Cả hai là đoạn mã minh họa trong một phương thức. Khi muốn phản hồi chính xác, nhánh thứ nhất phù hợp hơn; nhánh thứ hai phù hợp khi policy chỉ có một mã lỗi phiên bản không hợp lệ.

**Không nên** parse mọi số bằng `Long.parseLong` rồi tự kết luận `Runtime.Version` phải chấp nhận, vì một giá trị vẫn có thể vượt `Integer.MAX_VALUE` dù nằm trong phạm vi `long`.

### 5.1. Sai grammar và overflow là hai thứ khác nhau

- `021`: sai **hình dạng** chuỗi do leading zero.
- `2147483648`: đúng dạng các chữ số dương về mặt hình học, nhưng vượt giới hạn kiểu số.
- `21..2`: sai vì thiếu thành phần.
- `21+2147483648`: BUILD quá lớn.

Nếu ứng dụng hiển thị thông báo nhập liệu, nên dùng “cấu trúc không hợp lệ” cho nhóm đầu, và “số thành phần quá lớn” cho nhóm sau. Tránh dùng một câu “chưa hỗ trợ JDK này” để mô tả lỗi cú pháp: một bản JDK có thể chưa được phê duyệt dù chuỗi hoàn toàn hợp lệ.

## 6. Null và blank là chính sách của API ứng dụng, không phải parser

### 6.1. `null` không thuộc IllegalArgumentException

`Runtime.Version.parse(null)` ném `NullPointerException`. Vì vậy:

```java
try {
    Runtime.Version.parse(raw);
} catch (IllegalArgumentException ex) {
    // KHÔNG bắt được NullPointerException.
}
```

Nếu `raw` có thể là null từ JSON, môi trường, cấu hình hay hàm gọi khác, **nên kiểm tra trước** và trả mã lỗi rõ ràng:

```java
if (raw == null) {
    throw new IllegalArgumentException(
            "jdk.version must be supplied");
}
```

Đây là một **chính sách API** chuyển null thành validation error, không phải thay đổi hành vi gốc của `Runtime.Version.parse`.

### 6.2. Có nên trim khoảng trắng không?

Không có yêu cầu phải âm thầm sửa input:
- `" 21"` và `"21 "` có khoảng trắng ngoài version string.
- `Runtime.Version.parse` nhận **chuỗi phiên bản**, không phải toàn bộ dòng lệnh có prefix/suffix.
- Nếu dùng dữ liệu kiểm kê hoặc cấu hình bắt buộc khớp chính xác, nên **reject khoảng trắng** và yêu cầu sửa nguồn.
- Nếu có hợp đồng input UX cho phép whitespace, có thể gọi `strip()` trước parse, nhưng cần nói rõ đây là **normalization của ứng dụng**, không phải thuộc tính tự động của parser.

Trong lab, một policy chặt được chọn: `raw` chỉ bị chấp nhận nếu bằng chính `raw.strip()`; ngược lại báo `SURROUNDING_WHITESPACE`. Điều này giúp thấy rõ nơi xử lý whitespace.

Không dùng `strip()` để chữa chuỗi rỗng, leading zero, trailing zero hoặc phần build sai cú pháp. Các lỗi đó cần báo theo hợp đồng và không nên được âm thầm điều chỉnh.

### 6.3. Dữ liệu từ biến môi trường và file cấu hình

`System.getenv("JDK_VERSION")` có thể trả `null` nếu biến không tồn tại. Đây là ca thường gặp trong CI/CD. Nên:
1. Kiểm tra key có tồn tại.
2. Kiểm tra chuỗi có rỗng/blank hay không.
3. Quyết định normalization whitespace nếu đã được phép.
4. Parse bằng `Runtime.Version.parse`.
5. Áp dụng policy version tối thiểu.
6. Trả về lỗi rõ ràng nếu input sai và giữ nguyên giá trị raw để hỗ trợ chẩn đoán.

Đừng ép biến môi trường không tồn tại thành phiên bản JVM đang chạy khi policy muốn kiểm tra một JDK mục tiêu có thể **khác** runtime của tiến trình đang thực hiện kiểm tra.

## 7. Hai kiểu API xử lý lỗi: reject và trả kết quả có cấu trúc

### 7.1. Kiểu REJECT: throw với nguyên nhân được giữ

Khi một file cấu hình bắt buộc phải chứa chuỗi JDK hợp lệ:

```java
static Runtime.Version requiredVersion(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException(
                "Required JDK version is missing");
    }
    try {
        return Runtime.Version.parse(raw);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid JDK version string: " + raw, ex);
    }
}
```

Đây là phương thức minh họa đặt **trong class Java**. Nó trả về phiên bản hoặc ném lỗi, không nuốt exception. `new IllegalArgumentException(message,ex)` giữ nguyên nhân gốc (`getCause()`) để người vận hành điều tra.

Hạn chế: `null`/blank bị gộp thành “missing”, và chưa phân loại riêng overflow. Nếu cần thống kê chi tiết, dùng kết quả có cấu trúc ở phần tiếp theo.

### 7.2. Kiểu RESULT: không dùng exception cho nhánh input hợp lệ/sai thường gặp

Một validation service có thể trả:

```text
OK                    -> Runtime.Version đã parse
NULL_INPUT            -> raw == null
EMPTY_INPUT           -> raw.equals("")
SURROUNDING_WHITESPACE-> raw chứa khoảng trắng ở đầu hoặc cuối
INVALID_VERSION_SYNTAX-> Runtime.Version.parse ném IllegalArgumentException
NUMBER_OUT_OF_RANGE   -> Runtime.Version.parse ném NumberFormatException
```

Dữ liệu trả về nên giữ cả **giá trị** nếu thành công và **mã lỗi** nếu thất bại. Điều này thuận tiện cho UI form, job CI, endpoint REST và kiểm toán. Không cần invent một ngoại lệ tùy biến cho mọi lỗi parser nếu một result object đáp ứng nhu cầu.

Trong lab, sử dụng `record Outcome(Runtime.Version value, String reason)` với `value == null` thể hiện lỗi. Với hệ thống lớn, nên đổi `reason` thành enum, ví dụ `VersionError.NULL_INPUT`/`VersionError.INVALID_VERSION_SYNTAX` để tránh lỗi gõ chuỗi; có thể giữ source field, index, message của tầng ứng dụng và severity.

### 7.3. Policy reject không đồng nghĩa policy hỗ trợ JDK

Một chuỗi có thể parse đúng nhưng **không được phép dùng** trong production:
- `21-ea+28` hợp lệ về cú pháp, nhưng thường không được phép dùng nếu chỉ chấp nhận bản GA.
- `21.0.2+13-LTS` hợp lệ về cú pháp, nhưng chưa chắc là bản vá được tổ chức phê duyệt.
- `99` có thể hợp lệ về cú pháp nhưng không chỉ ra một JDK có thể tải/cài đặt thật.
- `17` hợp lệ nhưng có thể thấp hơn phiên bản tối thiểu của sản phẩm.

Vì vậy API nên tách:

```text
validate syntax -> parse Runtime.Version -> check product requirements
                                  |
                                  +-- feature minimum?
                                  +-- pre-release allowed?
                                  +-- vendor allowed?
                                  +-- update/build patch policy?
                                  +-- actual installed runtime?
```

**Không** coi `IllegalArgumentException` từ parser là trường hợp duy nhất cần xử lý để bảo đảm tương thích, an toàn hoặc vận hành.

## 8. Chương trình chạy được: phân loại lỗi và kiểm tra phiên bản hợp lệ

### 8.1. Yêu cầu môi trường

Dùng JDK **17+** còn được hỗ trợ và cập nhật bản vá, chẳng hạn JDK 21 hoặc 25 theo chính sách dự án. Chương trình sử dụng `record` (Java 16+) và `String.strip()` (Java 11+), cùng `Runtime.Version`.

Kiểm tra:

```bash
java -version
javac -version
```

Lưu toàn bộ mã sau thành **`InvalidVersionLab.java`**:

```java
public class InvalidVersionLab {
    // Kết quả có cấu trúc: value khác null khi parse thành công.
    record Outcome(Runtime.Version value, String reason) {
        boolean accepted() {
            return value != null;
        }

        String describe() {
            return accepted()
                    ? "OK " + value.toString()
                    : reason;
        }
    }

    static Outcome parseConfiguration(String raw) {
        // Null và policy whitespace được xử lý trước parse.
        if (raw == null) {
            return new Outcome(null, "NULL_INPUT");
        }
        if (raw.isEmpty()) {
            return new Outcome(null, "EMPTY_INPUT");
        }
        if (!raw.equals(raw.strip())) {
            return new Outcome(null, "SURROUNDING_WHITESPACE");
        }

        try {
            return new Outcome(
                    Runtime.Version.parse(raw), null);
        } catch (NumberFormatException ex) {
            // Bắt subclass trước.
            return new Outcome(
                    null, "NUMBER_OUT_OF_RANGE");
        } catch (IllegalArgumentException ex) {
            return new Outcome(
                    null, "INVALID_VERSION_SYNTAX");
        }
    }

    static void show(String name, String raw) {
        System.out.println(name + ": "
                + parseConfiguration(raw).describe());
    }

    public static void main(String[] args) {
        // Những chuỗi hợp lệ.
        show("feature only", "21");
        show("with update", "21.0.2");
        show("with patch", "21.0.2.1");
        show("early access", "21-ea+28");
        show("build and optional", "21.0.2+13-LTS");
        show("optional without build", "21+-LTS");

        // Sai grammar của VNUM/VSTR.
        show("trailing zero", "21.0.0");
        show("leading zero", "021");
        show("zero feature", "0");
        show("empty segment", "21..2");
        show("leading zero build", "21.0.2+03");
        show("empty build", "21.0.2+");
        show("banner not version", "openjdk version 21");

        // Policy do ứng dụng xác định.
        show("surrounding whitespace", " 21 ");
        show("empty", "");
        show("null", null);

        // Thành phần vượt Integer.MAX_VALUE.
        show("feature overflow", "2147483648");
        show("build overflow", "21+2147483648");

        // Phân tích giá trị đã được xác thực.
        Runtime.Version v =
                parseConfiguration("21.0.2+13-LTS").value();
        System.out.println("feature: " + v.feature());
        System.out.println("interim: " + v.interim());
        System.out.println("update: " + v.update());
        System.out.println("patch: " + v.patch());
        System.out.println("build: "
                + v.build().orElse(-1));
        System.out.println("optional: "
                + v.optional().orElse("none"));

        // So sánh cấu trúc số, không dùng String.compareTo.
        System.out.println("numeric 10 above 9: "
                + (Runtime.Version.parse("21.0.10")
                    .compareTo(
                            Runtime.Version.parse("21.0.9")) > 0));

        // Chứng minh raw null có exception khác.
        try {
            Runtime.Version.parse(null);
        } catch (NullPointerException ex) {
            System.out.println(
                    "raw null exception: NullPointerException");
        }

        // NumberFormatException là subclass của IllegalArgumentException.
        System.out.println(
                "NumberFormatException is IllegalArgumentException: "
                    + (new NumberFormatException()
                            instanceof IllegalArgumentException));
    }
}
```

### 8.2. Biên dịch, chạy

Trong thư mục chứa tệp:

```bash
javac InvalidVersionLab.java
java InvalidVersionLab
```

### 8.3. Stdout chính xác — 27 dòng

```text
feature only: OK 21
with update: OK 21.0.2
with patch: OK 21.0.2.1
early access: OK 21-ea+28
build and optional: OK 21.0.2+13-LTS
optional without build: OK 21+-LTS
trailing zero: INVALID_VERSION_SYNTAX
leading zero: INVALID_VERSION_SYNTAX
zero feature: INVALID_VERSION_SYNTAX
empty segment: INVALID_VERSION_SYNTAX
leading zero build: INVALID_VERSION_SYNTAX
empty build: INVALID_VERSION_SYNTAX
banner not version: INVALID_VERSION_SYNTAX
surrounding whitespace: SURROUNDING_WHITESPACE
empty: EMPTY_INPUT
null: NULL_INPUT
feature overflow: NUMBER_OUT_OF_RANGE
build overflow: NUMBER_OUT_OF_RANGE
feature: 21
interim: 0
update: 2
patch: 0
build: 13
optional: LTS
numeric 10 above 9: true
raw null exception: NullPointerException
NumberFormatException is IllegalArgumentException: true
```

Kết quả này dựa trên **các chuỗi fixture cố định**, không in phiên bản thực tế của JDK trên máy. Mọi bản JDK 17+ tuân thủ `Runtime.Version` hiện hành đều có thể chạy ví dụ; trên JDK đã kiểm thử, **27 dòng khớp chính xác**.

### 8.4. Giải thích nhóm dữ liệu hợp lệ

- `feature only: OK 21`: VNUM chỉ có FEATURE là hợp lệ.
- `with update: OK 21.0.2`: INTERIM 0 ở giữa FEATURE và UPDATE 2 hợp lệ.
- `with patch: OK 21.0.2.1`: PATCH 1 nằm sau dấu chấm thứ ba.
- `early access: OK 21-ea+28`: PRE=ea, BUILD=28.
- `build and optional: OK 21.0.2+13-LTS`: BUILD=13, OPT=LTS.
- `optional without build: OK 21+-LTS`: một trong các dạng VSTR có OPT mà không có BUILD.

Đối với ứng dụng cho phép tạo một đối tượng version để so sánh, chúng đều pass **cú pháp**. Nếu policy không chấp nhận EA hoặc chưa phê duyệt build có metadata LTS, cần thêm bước kiểm tra nghiệp vụ sau parse.

### 8.5. Giải thích nhóm lỗi cú pháp

- `trailing zero`: `21.0.0` không hợp lệ vì thành phần VNUM cuối là 0.
- `leading zero`: `021` không hợp lệ vì FEATURE có số 0 dư đầu.
- `zero feature`: `0` không hợp lệ vì FEATURE phải dương.
- `empty segment`: `21..2` thiếu một phần giữa dấu chấm.
- `leading zero build`: `21.0.2+03` có build number viết sai.
- `empty build`: `21.0.2+` thiếu thành phần sau dấu `+`.
- `banner not version`: `openjdk version 21` là lời mô tả, không phải VSTR.

Tất cả các input trên đều được hàm `parseConfiguration` chuyển về `INVALID_VERSION_SYNTAX` do `Runtime.Version.parse` ném `IllegalArgumentException`. Đây là **mã lỗi do ứng dụng chọn**, không phải tên trường enum do JDK cung cấp.

### 8.6. Giải thích null, whitespace và overflow

- `surrounding whitespace`: lab chọn policy không tự `strip` giá trị rồi chấp nhận; nó trả `SURROUNDING_WHITESPACE` trước khi parse.
- `empty` và `null`: hai loại input khác nhau, lần lượt trả `EMPTY_INPUT` và `NULL_INPUT`.
- `feature overflow` và `build overflow`: các thành phần `2147483648` vượt `Integer.MAX_VALUE`, nên `parse` ném `NumberFormatException` và helper phân loại thành `NUMBER_OUT_OF_RANGE`.

**Đừng gộp trường null và số tràn vào cùng một lỗi “phiên bản JDK quá cũ”.** Chúng là lỗi đầu vào khác với policy phiên bản tối thiểu.

### 8.7. Giải thích các trường version được đọc sau parse

`Runtime.Version.parse("21.0.2+13-LTS")` có:
- FEATURE=21, INTERIM=0, UPDATE=2, PATCH=0.
- BUILD=13.
- OPTIONAL=LTS.

Số 13 **không phải PATCH** vì sau dấu `+`. `patch()==0` là chính xác vì VNUM không có thành phần PATCH.

Dòng `numeric 10 above 9: true` xác nhận `21.0.10` lớn hơn `21.0.9` theo `Runtime.Version.compareTo`. Nếu so trực tiếp hai chuỗi bằng ký tự, kết quả có thể sai.

Hai dòng cuối cho thấy `parse(null)` ném `NullPointerException`, còn `NumberFormatException` thuộc nhánh `IllegalArgumentException`.

## 9. Viết unit tests với JUnit Jupiter

Chương trình ở phần 8 chạy **không cần thư viện ngoài**. Khi dự án đã có **JUnit Jupiter** trong build, nên viết unit tests trên lớp validation của chính ứng dụng.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class VersionValidationTest {
    @Test
    void parsesFeatureAndUpdate() {
        Runtime.Version v =
                Runtime.Version.parse("21.0.2");

        assertEquals(21, v.feature());
        assertEquals(0, v.interim());
        assertEquals(2, v.update());
        assertEquals(0, v.patch());
    }

    @Test
    void rejectsTrailingZero() {
        assertThrows(IllegalArgumentException.class,
                () -> Runtime.Version.parse("21.0.0"));
    }

    @Test
    void rejectsLeadingZeroInBuild() {
        assertThrows(IllegalArgumentException.class,
                () -> Runtime.Version.parse("21+03"));
    }

    @Test
    void detectsNumericOverflow() {
        assertThrows(NumberFormatException.class,
                () -> Runtime.Version.parse("2147483648"));
    }

    @Test
    void rejectsNullSeparately() {
        assertThrows(NullPointerException.class,
                () -> Runtime.Version.parse(null));
    }

    @Test
    void comparesNumbersNotText() {
        Runtime.Version a =
                Runtime.Version.parse("21.0.10");
        Runtime.Version b =
                Runtime.Version.parse("21.0.9");

        assertTrue(a.compareTo(b) > 0);
    }
}
```

Đây là **JUnit test class**, cần dependency và test runner Jupiter, không thể chỉ chạy `javac VersionValidationTest.java` trên JDK trống. Nó dùng JDK API chứ không giả định exact exception message.

Nếu muốn kiểm thử `parseConfiguration` của lab, có thể khai thác tính đóng gói của test package/class hoặc tách hàm validator sang class riêng. Sau đó xác nhận:
- `parseConfiguration(null).reason()` là `NULL_INPUT`.
- `parseConfiguration(" 21 ").reason()` là `SURROUNDING_WHITESPACE`.
- `parseConfiguration("2147483648").reason()` là `NUMBER_OUT_OF_RANGE`.
- `parseConfiguration("21").accepted()` là `true`.

Không nên kiểm tra output của `ex.toString()` chứa chính xác một bản dịch/thông điệp cố định.

## 10. Các quyết định chính sách validation trong hệ thống thực

### 10.1. Configuration gate: nên từ chối input không hợp lệ

Một tập tin cấu hình deployment có `requiredJavaVersion`. Nếu giá trị `"021"` sai grammar, nên trả lỗi cụ thể:

```text
CONFIGURATION_INVALID
field: requiredJavaVersion
reason: INVALID_VERSION_SYNTAX
provided: 021
expected: Java Runtime.Version string (for example 21 or 21.0.2)
```

Đây là **ví dụ định dạng lỗi ứng dụng**, không phải exception text có sẵn trong JDK. Vì giá trị nhỏ và không nhạy cảm, có thể ghi để debug nếu chính sách bảo mật cho phép; với input bất kỳ từ người dùng, cần giới hạn độ dài và loại bỏ ký tự điều khiển trước khi ghi log.

**Không** tự chuyển `"021"` thành `"21"` mà không có thỏa thuận. Một job CI có thể cần phát hiện lỗi dữ liệu thay vì chạy nhầm một bản runtime.

### 10.2. Validation không chứng minh bản JDK thực sự tồn tại

`Runtime.Version.parse("99")` có thể thành công chỉ vì cấu trúc là một số FEATURE dương. Nó **không tải JDK 99**, không kiểm tra file hệ thống, không xác minh vendor có bản build ấy và không bảo đảm ứng dụng chạy được với phiên bản đó.

Muốn kiểm tra runtime đang chạy:

```java
Runtime.Version running = Runtime.version();
int currentFeature = running.feature();
```

Đây là đoạn minh họa trong phương thức. Với CI toolchain, runtime nơi chạy công cụ có thể khác JDK dùng để build dự án. Phải xác định đúng đường dẫn `java`, `javac` và toolchain thực tế.

### 10.3. Chuỗi hợp lệ vẫn có thể không đạt version tối thiểu

Nếu policy yêu cầu Java FEATURE ít nhất 21:

```java
Runtime.Version parsed = Runtime.Version.parse(raw);
if (parsed.feature() < 21) {
    throw new IllegalArgumentException(
            "Java feature level is below required 21");
}
```

Đây là đoạn minh họa trong một method, giả định `raw` đã không null và đúng grammar. Ngoại lệ ở đây **do ứng dụng tự ném**, không phải lỗi parse.

Đừng diễn dịch `IllegalArgumentException` mà ứng dụng tự ném từ policy version tối thiểu thành “chuỗi sai cấu trúc”. Có thể xây mã lỗi khác nhau như `INVALID_VERSION_SYNTAX` và `MINIMUM_FEATURE_NOT_MET`.

### 10.4. Cấm pre-release/EA trong production

`21-ea+28` là version string hợp lệ. Tuy nhiên, nếu production chỉ cho phép GA:

```java
Runtime.Version parsed = Runtime.Version.parse(raw);
if (parsed.pre().isPresent()) {
    throw new IllegalArgumentException(
            "Pre-release runtime is not allowed");
}
```

Đây là kiểm tra nghiệp vụ riêng, không nên sửa `Runtime.Version.parse` để từ chối `PRE` hợp lệ. `pre().isEmpty()` cũng không tự chứng minh vendor còn hỗ trợ phiên bản đó; cần đối chiếu chính sách bản vá và phát hành.

### 10.5. Build/optional metadata không phải version security score

`21.0.2+13-LTS` có `BUILD=13` và `OPT=LTS`. Không được coi:
- `BUILD 13` là PATCH 13.
- `-LTS` là chứng chỉ bảo mật.
- Hai phiên bản cùng FEATURE chắc chắn nhận cùng mức vá lỗi.
- Runtime có FEATURE cao hơn luôn được tổ chức hỗ trợ hơn.

Version metadata giúp xác định build, nhưng quy trình compliance còn cần vendor, cập nhật bảo mật, lịch phát hành và chính sách hỗ trợ.

### 10.6. Nếu chấp nhận fallback, phải công bố

Một màn hình xem trước nội dung có thể được phép fallback về version mặc định. Trong trường hợp đó, nên lưu hai trường:

```text
requested_version: "21.0.0"
validation_result: INVALID_VERSION_SYNTAX
effective_version: "21"
fallback_reason: "Invalid input; using configured default"
```

Đây là minh họa hợp đồng sản phẩm. Nếu fallback ảnh hưởng đến quyết định cài đặt JDK, biên dịch, kiểm tra bảo mật hoặc giá trị vận hành quan trọng, thường nên **REJECT** thay vì lặng lẽ đổi version.

## 11. Khi nào không nên bắt IllegalArgumentException?

### 11.1. Không bắt quá rộng quanh một khối lớn

Ví dụ:

```java
try {
    configureDatabase();
    Runtime.Version version = Runtime.Version.parse(raw);
    deployApplication(version);
} catch (IllegalArgumentException ex) {
    report("Invalid JDK version");
}
```

Đây là mã giả **không độc lập** với những hàm chưa định nghĩa. Một `IllegalArgumentException` từ `configureDatabase` hoặc `deployApplication` có thể bị quy nhầm là lỗi version. Thay vì vậy, **thu hẹp try/catch chỉ quanh `Runtime.Version.parse(raw)`**, rồi áp dụng các bước tiếp theo ở scope khác.

### 11.2. Không bắt NullPointerException trên toàn ứng dụng để “sửa input”

Mặc dù `Runtime.Version.parse(null)` có thể ném `NullPointerException`, không nên dùng:

```java
try {
    // Một luồng xử lý lớn...
} catch (NullPointerException ex) {
    // Coi mọi lỗi là thiếu version.
}
```

Cách này che lỗi lập trình ở những chỗ không liên quan. Kiểm tra `raw == null` tại boundary input, với mã lỗi `NULL_INPUT`. Nếu thật sự bắt `NullPointerException` quanh một lời gọi duy nhất, hãy giữ phạm vi hẹp và có ngữ cảnh rõ.

### 11.3. Không dùng exception để thay thế policy nghiệp vụ

Một chuỗi hợp lệ nhưng thấp hơn version tối thiểu là **không đạt policy**, không phải parse failure. Một chuỗi hợp lệ có metadata vendor không được phê duyệt cũng cần xử lý theo rule riêng.

Tách các lớp:
- **Input validation:** null, empty, whitespace.
- **Java grammar parse:** `Runtime.Version.parse`.
- **Runtime compatibility:** feature, pre-release, class-file format, API availability.
- **Operations/compliance:** vendor, update/patch, lịch hỗ trợ và bản vá.

Mỗi lớp nên có mã lỗi rõ để giúp người dùng sửa đúng nguyên nhân.

## 12. Câu hỏi thường gặp

### 12.1. `NumberFormatException` có bị `catch(IllegalArgumentException)` bắt không?

**Có.** `NumberFormatException` kế thừa `IllegalArgumentException`. Nếu muốn thông báo cụ thể “component quá lớn”, đặt `catch(NumberFormatException)` trước `catch(IllegalArgumentException)`. Nếu chỉ muốn một thông báo “version không hợp lệ”, một nhánh `IllegalArgumentException` có thể đủ.

### 12.2. `Runtime.Version.parse(null)` có trả `Optional.empty()` không?

**Không.** Phương thức trả `Runtime.Version` trực tiếp nếu thành công, và ném `NullPointerException` với null. Muốn API không ném exception ở boundary, tự viết wrapper trả `Optional`, `Either` hoặc result object tùy thiết kế.

### 12.3. `Runtime.Version.parse("21.0.0")` có tự đổi thành `21` không?

**Không.** `$VNUM` không cho phép thành phần 0 cuối; parser ném `IllegalArgumentException`. Không mặc nhiên “chữa” lỗi này bằng cách cắt phần số 0.

### 12.4. Có thể lấy riêng `FEATURE` bằng `input.split("\\.")[0]` không?

Không nên dùng đó như một bộ kiểm tra phiên bản hợp lệ. Với `21-ea`, phần đầu cũng chứa `-ea`, và với input sai bạn có thể đọc được một số nhưng bỏ qua lỗi ở phần sau. Parse toàn chuỗi trước, rồi gọi `feature()`.

### 12.5. Có thể dùng `try/catch` để đoán nhà phân phối có phát hành bản JDK không?

Không. Parse chỉ kiểm tra grammar và giới hạn số nguyên. Muốn kiểm tra bản build có thật, cần dựa vào nguồn bản phát hành được nhà cung cấp công bố, hoặc runtime JDK đã cài đặt.

### 12.6. Có được gọi `System.getProperty("java.version")` rồi parse?

Có thể, nhưng cần phân biệt giá trị của system property với `Runtime.version()`. `Runtime.version()` là API trực tiếp để lấy đối tượng version của JVM hiện tại. Một số bản phân phối có thể biểu diễn thuộc tính `java.version` ngắn hơn version string chứa BUILD/OPT.

### 12.7. Đã parse hợp lệ rồi thì có thể so bằng chuỗi không?

Không nên. `"21.0.10"` đứng sau `"21.0.9"` theo số học, nhưng `String.compareTo` xét từng ký tự. Dùng `Runtime.Version.compareTo` và cân nhắc `compareToIgnoreOptional` nếu muốn bỏ optional metadata.

### 12.8. `NumberFormatException` có thể đến từ policy của tôi thay vì parser không?

Có, nếu bạn dùng thêm `Integer.parseInt` hoặc các parser riêng. Vì vậy chỉ bắt `NumberFormatException` quanh `Runtime.Version.parse` trong phần validation này để xác định được nguyên nhân. Không bọc một khối dài có nhiều phép chuyển đổi số rồi quy tất cả thành lỗi JDK version.

## 13. Bài tập có đáp án

### Bài 1 — Tra ngoại lệ

```java
Runtime.Version.parse("21.0.0");
```

**Đáp án:** `IllegalArgumentException` vì `$VNUM` có thành phần 0 ở cuối. Không tự chuẩn hóa input.

### Bài 2 — Phân biệt số 0 ở giữa

`Runtime.Version.parse("21.0.2")` có hợp lệ không? Các getter trả gì?

**Đáp án:** Có. `feature()==21`, `interim()==0`, `update()==2` và `patch()==0`. Số 0 ở giữa cần thiết để biểu diễn UPDATE=2.

### Bài 3 — Leading zero ở FEATURE

`Runtime.Version.parse("021")` hợp lệ không, dù `Integer.parseInt("021")==21`?

**Đáp án:** Không. Grammar JDK cấm leading zero. `Integer.parseInt` không tương đương parser phiên bản.

### Bài 4 — Leading zero ở BUILD

`Runtime.Version.parse("21.0.2+03")` có hợp lệ không?

**Đáp án:** Không. `BUILD` là số nguyên không âm nhưng không có leading zero, trừ chính `0`. Parser từ chối.

### Bài 5 — Overflow và phân cấp exception

`Runtime.Version.parse("2147483648")` ném loại nào? `catch(IllegalArgumentException)` có bắt được không?

**Đáp án:** Ném `NumberFormatException` vì giá trị vượt `Integer.MAX_VALUE`. Có, vì `NumberFormatException` là lớp con `IllegalArgumentException`.

### Bài 6 — Đối số null

`Runtime.Version.parse(null)` có đi vào `catch(IllegalArgumentException)` không?

**Đáp án:** Không. Nó ném `NullPointerException`, không phải subtype của `IllegalArgumentException`. Nên xử lý null ở boundary.

### Bài 7 — Nội dung chuỗi đúng nhưng không được phép dùng

`"21-ea+28"` parse thành công. Có đủ điều kiện để triển khai trên production khi chính sách cấm EA?

**Đáp án:** Không. Parser chấp nhận grammar hợp lệ. Policy cần kiểm tra `pre().isPresent()` và reject pre-release nếu có quy định.

### Bài 8 — Banner không phải version

Vì sao `Runtime.Version.parse("openjdk version 21")` thất bại?

**Đáp án:** Đây là text mô tả, không phải `$VSTR`. Lấy version string qua API/nguồn phù hợp, không lấy toàn bộ banner.

### Bài 9 — Result object

Trong lab, `parseConfiguration(" 21 ")` trả lỗi gì? Do Java parser tự phát hiện hay do policy?

**Đáp án:** `SURROUNDING_WHITESPACE`. Đây là lựa chọn **của ứng dụng**, trả về trước khi `Runtime.Version.parse` được gọi. Ứng dụng khác có thể cho phép `strip` nếu chính sách cho phép.

### Bài 10 — Số không hợp lệ và số không được hỗ trợ

`Runtime.Version.parse("99")` thành công; có thể kết luận JDK 99 đã được cài và nhận bản vá không?

**Đáp án:** Không. Parse chỉ chứng minh chuỗi hợp lệ. Cần kiểm tra bộ JDK cài thật, vendor, release notes và chính sách hỗ trợ.

### Bài 11 — Cách đặt catch đúng

```java
try {
    Runtime.Version.parse(raw);
} catch (IllegalArgumentException ex) {
    // A
} catch (NumberFormatException ex) {
    // B
}
```

**Đáp án:** Không biên dịch vì `NumberFormatException` là subtype và đã bị bắt bởi nhánh A. Đảo thứ tự subclass trước superclass hoặc chỉ bắt `IllegalArgumentException` nếu không cần phân loại.

### Bài 12 — Kiểm tra phiên bản tối thiểu

`Runtime.Version.parse("17")` hợp lệ, nhưng sản phẩm yêu cầu FEATURE từ 21 trở lên. Lỗi nên được phân loại là gì?

**Đáp án:** **MINIMUM_FEATURE_NOT_MET** hoặc mã policy tương ứng, không phải `INVALID_VERSION_SYNTAX`. Parser đã thành công.

### Bài 13 — Giữ nguyên nguyên nhân

Tại sao nên dùng `new IllegalArgumentException("Invalid version: " + raw, ex)` khi bọc lỗi từ parser?

**Đáp án:** Giữ được `cause` ban đầu, hữu ích cho debug và phân loại. Không nên ghi raw input quá dài hoặc chứa bí mật vào log/exception nếu chưa kiểm soát.

### Bài 14 — So sánh sau parse

`21.0.10` và `21.0.9`, phiên bản nào lớn hơn? Vì sao không dùng `String.compareTo`?

**Đáp án:** `21.0.10` lớn hơn theo `Runtime.Version.compareTo` vì UPDATE 10 lớn hơn UPDATE 9. So chuỗi xét ký tự, có thể cho thứ tự sai.

### Bài 15 — Version number và build

`21.0.2+13` có `patch()` bao nhiêu? `build()` bao nhiêu?

**Đáp án:** `patch()==0`, `build().orElse(-1)==13`. Dấu `+` không biểu diễn PATCH.

### Bài 16 — Unit tests độc lập môi trường

Tại sao test `assertEquals(21, Runtime.version().feature())` không portable?

**Đáp án:** Vì JVM hiện tại có thể là JDK 17, 21, 25 hoặc phiên bản mới hơn. Unit test cho parser nên dùng fixtures như `Runtime.Version.parse("21.0.2")`; runtime compatibility test nên kiểm tra ràng buộc thực sự như `feature()>=17` nếu đúng với môi trường hỗ trợ.

## 14. Checklist khi code review

- [ ] Chỉ gọi `Runtime.Version.parse` với **version string**, không phải toàn bộ banner dòng lệnh, URL hay tên bản cài.
- [ ] Dùng cấu trúc JEP 322: FEATURE.INTERIM.UPDATE.PATCH; không giới thiệu tên accessor deprecated trong mã mới.
- [ ] Kiểm tra `null` trước khi parse nếu muốn validation error có cấu trúc.
- [ ] Quyết định rõ có chấp nhận `""`, blank, whitespace đầu/cuối hay không.
- [ ] Dùng `Runtime.Version.parse` làm parser duy nhất cho grammar JDK; không tự split rồi cho pass.
- [ ] Biết số 0 **ở giữa** hợp lệ, nhưng VNUM không có thành phần 0 **cuối**.
- [ ] Không chấp nhận leading zero trong thành phần số hoặc BUILD.
- [ ] Bắt `NumberFormatException` **trước** `IllegalArgumentException` nếu muốn phân loại overflow.
- [ ] Không nghĩ `catch(IllegalArgumentException)` bắt được `NullPointerException`.
- [ ] Thu hẹp phạm vi catch quanh đúng lời gọi parse, không che exception từ phần mềm khác.
- [ ] Không phụ thuộc text `getMessage()` của exception trong test hay nghiệp vụ.
- [ ] Nếu cần bọc lỗi, giữ `cause` và thông tin nguồn đầu vào đủ an toàn.
- [ ] Không tự sửa input sai grammar thành version hợp lệ nếu không có chính sách rõ.
- [ ] Không coi kết quả parse thành công là bảo đảm JDK có thật, được cài, được hỗ trợ hay an toàn.
- [ ] Tách validation grammar với minimum FEATURE, policy EA/GA, vendor và security updates.
- [ ] Dùng `compareTo` thay so sánh version như chuỗi text.
- [ ] Test với cả positive fixtures, invalid syntax, overflow, null và whitespace.
- [ ] Không hardcode exact phiên bản Runtime đang chạy trong unit test.
- [ ] Chạy `InvalidVersionLab.java` và đối chiếu đủ **27 dòng stdout**.

## 15. Kết luận

**`Runtime.Version.parse(String)` kiểm tra chuỗi phiên bản JDK theo grammar hiện đại, không phải trạng thái cài đặt hay bảo mật của Java.** Nếu chuỗi sai cú pháp, nó ném `IllegalArgumentException`; nếu thành phần số hoặc BUILD quá lớn cho `Integer`, nó ném `NumberFormatException` (là subclass của `IllegalArgumentException`); nếu input là `null`, nó ném `NullPointerException`.

Khi phát triển API hoặc công cụ CI/CD, nên xử lý null/blank riêng, parse trong phạm vi try/catch hẹp, trả mã lỗi có cấu trúc, không âm thầm chữa chuỗi hỏng và kiểm tra các chính sách vận hành **sau khi parse thành công**. Các nguyên tắc này áp dụng tốt cho JDK hiện đại và tiếp tục hữu ích dù chu kỳ phát hành Java thay đổi.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 — Runtime.Version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): grammar `$VNUM/$VSTR`, `parse(String)`, `IllegalArgumentException`, `NumberFormatException`, `NullPointerException`, các getter và comparator.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình Java 10 FEATURE.INTERIM.UPDATE.PATCH và phần PRE/BUILD/OPT.
- [Oracle Java SE 25 — Runtime.version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#version()): lấy object version của JVM đang chạy.
- [Oracle Java SE 25 — IllegalArgumentException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IllegalArgumentException.html): ngoại lệ cho tham số không hợp lệ.
- [Oracle Java SE 25 — NumberFormatException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NumberFormatException.html): lỗi chuyển đổi số và quan hệ kế thừa với `IllegalArgumentException`.
- [Oracle Java SE 25 — NullPointerException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NullPointerException.html): trường hợp tham số null.
- [Oracle Java SE 25 — Runtime.Version.parse](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html#parse(java.lang.String)): tham chiếu trực tiếp cho lời gọi `parse` và các điều kiện ném exception.