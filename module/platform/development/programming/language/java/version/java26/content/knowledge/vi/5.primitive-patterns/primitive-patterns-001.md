# Java 26 preview lần 4; Java 27 tiếp tục preview lần 5

Primitive patterns mở rộng pattern matching của Java để làm việc trực tiếp với các kiểu nguyên thủy như `int`, `long`, `double` và `boolean`. Tính năng này cho phép kiểm tra một giá trị có thể chuyển đổi chính xác sang kiểu nguyên thủy nào, khai báo biến pattern mang kiểu nguyên thủy, dùng các pattern đó trong `instanceof`, `switch` và thành phần của record pattern.

Tính năng vẫn ở trạng thái preview trong Java 26 và Java 27. Java 26 đưa ra lần preview thứ tư qua JEP 530; Java 27 tiếp tục ở lần preview thứ năm qua JEP 532. Theo Java SE 27 Language Specification, lần preview thứ năm không có thay đổi chuẩn tắc về ngữ nghĩa so với đề xuất trước đó. Vì vậy, có thể học và thử nghiệm trên JDK 27, nhưng chưa nên dùng tính năng này làm hợp đồng ngôn ngữ ổn định cho ứng dụng production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích primitive type pattern và phân biệt nó với type pattern dành cho reference type.
- Dùng `instanceof` để kiểm tra một phép chuyển đổi nguyên thủy có chính xác hay không.
- Dùng primitive patterns trong `switch` và record patterns.
- Hiểu vì sao pattern chỉ khớp khi phép chuyển đổi không mất thông tin và không ném exception.
- Nhận biết thay đổi về exactness và dominance trong Java 26, cùng trạng thái preview lần thứ năm trong Java 27.
- Biên dịch và chạy ví dụ bằng đúng JDK với `--enable-preview`, đồng thời đánh giá rủi ro khi nâng cấp.

## 1. Lịch sử preview và trạng thái hiện tại

Primitive patterns được phát triển qua nhiều bản JDK:

| Java SE | JEP | Trạng thái |
|---|---|---|
| 23 | JEP 455 | Preview lần đầu |
| 24 | JEP 488 | Preview lần 2 |
| 25 | JEP 507 | Preview lần 3 |
| 26 | JEP 530 | Preview lần 4; cải tiến exactness và siết kiểm tra dominance trong `switch` |
| 27 | JEP 532 | Preview lần 5; không có thay đổi chuẩn tắc về ngữ nghĩa so với lần trước |

Tại thời điểm hiện tại, JDK 27 đã phát hành chính thức, nhưng primitive patterns vẫn là preview feature. JDK 27 là bản feature release không phải LTS; Java 25 hiện là bản LTS. Số lần preview cho thấy đặc tả vẫn được hoàn thiện, không phải dấu hiệu rằng cú pháp đã ổn định để mọi ứng dụng có thể phụ thuộc lâu dài.

Các phần pattern matching cho reference type đã được chuẩn hóa ở những phiên bản Java trước. Bài này chỉ sử dụng primitive patterns và các phần mở rộng liên quan; không nhầm chúng với type pattern thông thường đã trở thành tính năng chính thức.

## 2. Primitive pattern giải quyết vấn đề gì?

Trước primitive patterns, type pattern thường kiểm tra một reference có thuộc kiểu reference mong muốn hay không:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Primitive patterns mở rộng cách viết đó sang kiểu nguyên thủy:

```java
Object value = Integer.valueOf(42);

if (value instanceof int number) {
    System.out.println(number + 1);
}
```

Nếu giá trị bên trong `value` có thể chuyển đổi chính xác thành `int`, pattern khớp và biến `number` được khởi tạo bằng giá trị kiểu `int`. Với `Integer.valueOf(42)`, phép chuyển đổi gồm unboxing từ `Integer` sang `int` và không làm mất dữ liệu.

Primitive patterns cũng hỗ trợ kiểm tra narrowing conversion an toàn:

```java
static void printByteIfExact(int value) {
    if (value instanceof byte small) {
        System.out.println("Giá trị byte: " + small);
    } else {
        System.out.println("Không thể chuyển sang byte mà giữ nguyên giá trị");
    }
}
```

Với `value = 10`, pattern `byte small` khớp. Với `value = 1000`, pattern không khớp vì chuyển `1000` sang `byte` sẽ làm mất thông tin. Phép thử không trả về một giá trị đã bị cắt cụt để chương trình vô tình dùng nhầm.

## 3. Exact testing conversion: chỉ khớp khi giữ nguyên thông tin

Quy tắc cốt lõi của primitive patterns là phép chuyển đổi dùng để thử pattern phải *exact*: kết quả không được mất thông tin và không được ném exception. Nếu một phép chuyển đổi gồm nhiều bước, tất cả các bước phải exact thì toàn bộ phép thử mới thành công.

Các tình huống thường gặp:

| Kiểu nguồn | Pattern đích | Điều kiện khớp |
|---|---|---|
| `int` | `long` | Luôn khớp vì widening conversion giữ nguyên giá trị |
| `int` | `byte` | Chỉ khớp nếu giá trị nằm trong miền `byte` |
| `double` | `int` | Chỉ khớp nếu chuyển đổi không mất phần thập phân, dấu, miền hoặc thông tin khác |
| `Integer` | `int` | Khớp nếu reference không phải `null` và unboxing thành công |
| `Object` chứa `Integer` | `int` | Khớp nếu kiểm tra kiểu reference, unboxing và chuyển đổi đều thành công, chính xác |

Ví dụ, kiểm tra `double` có thể biểu diễn chính xác thành `int`:

```java
static boolean isExactInt(double value) {
    return value instanceof int number;
}
```

`12.0` có thể khớp vì chuyển sang `int` vẫn là `12`. `12.5`, `Double.NaN` và vô cực không khớp vì phép chuyển đổi sang `int` không giữ nguyên giá trị. Tương tự, chuyển `long` sang `double` có thể mất độ chính xác ở một số giá trị lớn; không thể coi mọi widening conversion đều exact.

Đặc tả xác định exactness dựa trên việc so sánh giá trị trong một kiểu trung gian được chọn theo cặp kiểu nguồn và đích. Với `int` sang `byte`, chẳng hạn, kiểm tra phải phát hiện cả mất dấu và mất độ lớn. Không nên tự thay quy tắc ngôn ngữ bằng một phép ép kiểu rồi giả định rằng ép ngược về kiểu ban đầu luôn phát hiện được mất dữ liệu.

`null` không phải giá trị nguyên thủy. Khi biểu thức nguồn là reference `null`, primitive type pattern không khớp. Điều này cũng tránh việc unboxing `null` tạo ra `NullPointerException` trong quá trình thử pattern.

## 4. Dùng primitive patterns với `instanceof`

`instanceof` có thể được dùng theo hai dạng:

- Type comparison: kiểm tra một giá trị có thể chuyển đổi chính xác sang kiểu được nêu hay không, không khai báo biến pattern.
- Pattern matching: kiểm tra và đồng thời khai báo biến pattern để sử dụng nếu phép thử thành công.

Ví dụ:

```java
static void inspect(Object value) {
    if (value instanceof int) {
        System.out.println("Có thể chuyển đổi chính xác sang int");
    }

    if (value instanceof int number) {
        System.out.println("Giá trị int: " + number);
    }
}
```

Hai biểu thức trên không có nghĩa rằng mọi object đều là instance của lớp `int`. Kiểu nguyên thủy không phải class. Chúng kiểm tra testing conversion từ kiểu tĩnh của biểu thức sang `int`, bao gồm các bước reference conversion hoặc unboxing cần thiết và kiểm tra tính exact ở runtime.

Ví dụ kiểm tra dữ liệu đầu vào từ một API trả về `Object`:

```java
static int parseCount(Object raw) {
    if (raw instanceof int count && count >= 0) {
        return count;
    }
    throw new IllegalArgumentException("Count phải là số nguyên không âm");
}
```

Đoạn mã chấp nhận giá trị có thể chuyển đổi chính xác thành `int`, chẳng hạn một `Integer` hợp lệ. Nó từ chối `null`, chuỗi, giá trị số không thể chuyển đổi chính xác hoặc kiểu không tương thích. Trong ứng dụng thực tế, hãy xác định rõ kiểu dữ liệu đầu vào mà API cho phép để thông báo lỗi phù hợp với hợp đồng của API.

## 5. Dùng primitive patterns trong `switch`

`switch` được mở rộng để làm việc với các kiểu nguyên thủy và các pattern có phép chuyển đổi phù hợp. Ví dụ sau phân loại một giá trị `double` theo khả năng chuyển đổi chính xác sang các kiểu số khác:

```java
static String classify(double value) {
    return switch (value) {
        case int number -> "Giá trị int chính xác: " + number;
        case long number -> "Giá trị long chính xác: " + number;
        case double number -> "Giá trị double: " + number;
    };
}
```

Ví dụ minh họa:

| Đầu vào | Nhánh khớp | Lý do |
|---:|---|---|
| `12.0` | `case int` | Chuyển thành `int` mà không mất dữ liệu |
| `3000000000.0` | `case long` | Không nằm trong miền `int`, nhưng chuyển thành `long` chính xác |
| `12.5` | `case double` | Không thể chuyển thành `int` hoặc `long` mà giữ nguyên phần thập phân |
| `Double.NaN` | `case double` | Chuyển sang kiểu nguyên không exact |

`case double number` đặt cuối vì nó khớp mọi giá trị `double` và do đó là pattern không điều kiện đối với selector kiểu `double`. Nếu đặt trước một pattern hẹp hơn, các nhánh sau sẽ không thể được chọn và compiler sẽ báo lỗi dominance.

`switch` expression phải exhaustive. Trong ví dụ trên, nhánh `double` bao phủ các giá trị còn lại. Với selector là wrapper hoặc reference type, hãy chú ý `null`: `null` không nằm trong miền giá trị của primitive type pattern. Nếu đầu vào có thể null, xử lý rõ ràng bằng `case null` hoặc kiểm tra trước khi switch; không dựa vào primitive pattern để xử lý null.

## 6. Primitive patterns trong record patterns

Primitive patterns có thể xuất hiện ở thành phần của record pattern. Điều này hữu ích khi record lưu dữ liệu tổng quát hoặc wrapper nhưng phần xử lý cần một kiểu nguyên thủy:

```java
record Reading(Object rawValue) {}

static void printReading(Object input) {
    if (input instanceof Reading(int value)) {
        System.out.println("Reading: " + value);
    } else {
        System.out.println("Không có reading int chính xác");
    }
}
```

Với `new Reading(Integer.valueOf(25))`, record pattern có thể khớp và biến `value` nhận `25`. Nếu thành phần là chuỗi, số không chuyển đổi chính xác hoặc `null`, pattern không khớp. Việc đọc component được thực hiện thông qua accessor của record; nếu accessor kết thúc bất thường, quá trình match có thể kết thúc bằng `MatchException` theo quy tắc record pattern.

Kỹ thuật này không thay thế việc thiết kế kiểu dữ liệu rõ ràng. Nếu record luôn đại diện cho một số nguyên, khai báo component là `int` hoặc `Integer` thường dễ hiểu hơn `Object`. Primitive pattern hữu ích khi xử lý dữ liệu có kiểu động hoặc khi cần phân nhánh theo khả năng chuyển đổi chính xác.

## 7. Những thay đổi đáng chú ý ở Java 26 preview lần 4

Java 26 tiếp tục tính năng qua JEP 530 và điều chỉnh hai phần quan trọng so với lần preview trước.

### Exactness và unconditionally exact conversion

Đặc tả phân biệt:

- **Exact testing conversion:** một giá trị cụ thể chuyển đổi mà không mất thông tin và không ném exception.
- **Type-based unconditionally exact conversion:** có thể xác định từ kiểu nguồn và kiểu đích rằng mọi giá trị phù hợp đều chuyển đổi chính xác.
- **Value-based unconditionally exact conversion:** có thể xác định một constant expression cụ thể chuyển đổi chính xác, dù phép chuyển đổi nói chung không luôn exact với mọi giá trị của kiểu nguồn.

Sự phân biệt này giúp compiler xác định pattern nào luôn khớp, switch nào exhaustive và nhánh nào bị dominance. Nó cũng ngăn compiler đưa ra kết luận sai khi một phép widening có thể mất độ chính xác, ví dụ `int` sang `float` hoặc `long` sang `double`.

### Kiểm tra dominance trong `switch` chặt hơn

Một case bị dominated nếu mọi giá trị mà nó có thể khớp đều đã được một nhánh đứng trước xử lý. Java 26 mở rộng kiểm tra này dựa trên các conversion được xác định là unconditionally exact, bao gồm một số constant expression.

Ví dụ:

```java
static String describe(Integer value) {
    return switch (value) {
        case Integer number -> "Integer: " + number;
        case 42 -> "Forty two"; // Compile-time error: bị dominated
    };
}
```

Pattern `Integer number` đã khớp mọi giá trị `Integer` không null, nên nhánh hằng `42` không thể được chọn. Hãy đặt các nhánh cụ thể trước nhánh tổng quát và không khai báo case mà compiler xác định là không thể tới.

Ví dụ khác về pattern không điều kiện:

```java
static String describe(int value) {
    return switch (value) {
        case byte small -> "byte range: " + small;
        case short medium -> "short range: " + medium;
        case int number -> "int: " + number;
    };
}
```

Các pattern hẹp hơn được thử trước; `case int` là pattern không điều kiện với selector kiểu `int`, nên đặt cuối để bao phủ mọi giá trị còn lại. Khi thay đổi thứ tự case, compiler có thể báo lỗi dominance vì nhánh trước đã bao phủ nhánh sau.

## 8. Java 27 preview lần 5: điều gì thay đổi?

Java 27 tiếp tục primitive patterns qua JEP 532. Java SE 27 Language Specification ghi nhận lần preview thứ năm và nêu rõ không có thay đổi chuẩn tắc đối với ngôn ngữ được đề xuất. Tài liệu đặc tả được cập nhật để đồng bộ với JLS của Java 27 và các liên kết API/spec tương ứng.

Điều này có nghĩa ví dụ và nguyên tắc exactness, pattern matching, switch exhaustiveness và dominance trong bài vẫn là cơ sở phù hợp để thử nghiệm trên JDK 27. Tuy nhiên, trạng thái vẫn là preview. Không nên hiểu việc Java 27 đã GA là primitive patterns cũng đã trở thành tính năng chính thức; vòng đời của JDK và trạng thái của từng JEP là hai việc riêng biệt.

## 9. Biên dịch và chạy với preview đúng JDK

Preview feature chỉ được biên dịch bằng JDK của chính release đang preview tính năng đó. Dùng JDK 26 cho preview lần 4 hoặc JDK 27 cho preview lần 5:

**JDK 26 — JEP 530:**

```bash
javac --release 26 --enable-preview -Xlint:preview PrimitivePatternsDemo.java
java --enable-preview PrimitivePatternsDemo
```

**JDK 27 — JEP 532:**

```bash
javac --release 27 --enable-preview -Xlint:preview PrimitivePatternsDemo.java
java --enable-preview PrimitivePatternsDemo
```

Kiểm tra `java --version` và `javac --version` trước khi chạy. Compiler và runtime phải cùng phiên bản preview. Ví dụ, không dùng JDK 27 để bật preview của Java 26 bằng cách chỉ đặt `--release 26`; `--enable-preview` chỉ bật preview của release JDK hiện tại.

Nếu dùng Maven hoặc Gradle, cấu hình `--enable-preview` cho cả tác vụ biên dịch và JVM chạy test/ứng dụng. Chỉ thêm cờ cho source set hoặc module thực sự dùng tính năng này. Không bật preview toàn repository nếu các module khác không cần nó.

## 10. Khi nào nên sử dụng?

Primitive patterns hữu ích trong những trường hợp cần kiểm tra dữ liệu số động, giải mã giá trị từ object/wrapper, phân nhánh theo khả năng chuyển đổi không mất dữ liệu hoặc xử lý record có component tổng quát. Nó có thể giảm các đoạn kiểm tra wrapper, ép kiểu và xử lý ngoại lệ thủ công.

Tuy nhiên, vì đây vẫn là preview:

- Không công bố API thư viện production phụ thuộc vào cú pháp preview.
- Không lưu class file được biên dịch với preview để triển khai trên runtime khác release.
- Không bật preview trên production chỉ để dùng cú pháp đang thử nghiệm.
- Giữ logic chuyển đổi dữ liệu quan trọng có test cho biên giá trị, overflow, floating-point, `NaN`, vô cực và `null`.
- Khi tính năng được chuẩn hóa ở một JDK tương lai, đọc JEP và release notes của chính release đó trước khi bỏ cờ preview hoặc thay đổi source level.

Nếu ứng dụng cần chạy production hiện nay, tiếp tục dùng API và pattern matching đã được chuẩn hóa trong JDK mục tiêu; kiểm tra dữ liệu số bằng các phép so sánh miền và chuyển đổi tường minh khi cần. Chỉ chuyển sang primitive patterns sau khi tính năng trở thành final trong một release được ứng dụng hỗ trợ.

## 11. Bài tập thực hành

Viết một chương trình kiểm tra dữ liệu nhận từ một nguồn trả về `Object`. Chương trình cần nhận số nguyên, từ chối dữ liệu không hợp lệ và phân loại giá trị `double` theo kiểu số có thể biểu diễn chính xác.

**Yêu cầu:**

1. Viết `parseCount(Object raw)` dùng `instanceof int count` để chấp nhận giá trị chuyển đổi chính xác thành `int` không âm.
2. Viết hàm kiểm tra một `int` có chuyển thành `byte` chính xác hay không.
3. Viết `switch` expression nhận `double`, thử `int`, sau đó `long`, rồi dùng `double` làm nhánh bao phủ cuối cùng.
4. Tạo record `Reading(Object rawValue)` và dùng record pattern `Reading(int value)` để đọc dữ liệu.
5. Chạy ví dụ trên JDK 26 và JDK 27 với đúng cờ preview của từng JDK.
6. Thử các trường hợp `null`, `Integer`, chuỗi, số ngoài miền `byte`, số thập phân, `NaN` và vô cực.
7. Giải thích vì sao tính năng chưa được xem là API/ngôn ngữ ổn định cho production.

**Kết quả mong đợi:**

- Giá trị `Integer` hợp lệ có thể được unbox để khớp `int` pattern.
- `int` chỉ khớp `byte` khi chuyển đổi không mất dữ liệu.
- `double` nguyên có thể khớp `int` hoặc `long` nếu biểu diễn chính xác; số thập phân không khớp các nhánh nguyên.
- Nhánh `double` cuối cùng làm `switch` expression exhaustive.
- `null` không khớp primitive pattern; dữ liệu không hợp lệ được xử lý rõ ràng.
- Cả JDK 26 preview lần 4 và JDK 27 preview lần 5 đều yêu cầu `--enable-preview` trên đúng phiên bản JDK tương ứng.

## Tài liệu tham khảo

- [JEP 530: Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): đề xuất preview lần thứ tư trong JDK 26.
- [Java SE 26 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://docs.oracle.com/javase/specs/jls/se26/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html): quy tắc chuyển đổi, exactness, pattern matching, switch và dominance của Java 26.
- [Java Language Changes by Release — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): lịch sử preview và các điều chỉnh của JEP 530.
- [JEP 532: Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532): đề xuất preview lần thứ năm trong JDK 27.
- [Java SE 27 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://docs.oracle.com/en/java/javase/27/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): đặc tả preview Java 27 và xác nhận không có thay đổi chuẩn tắc về ngữ nghĩa.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): trạng thái JEP 532 trong Java 27.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html): thông tin phát hành và cập nhật JDK 27.
