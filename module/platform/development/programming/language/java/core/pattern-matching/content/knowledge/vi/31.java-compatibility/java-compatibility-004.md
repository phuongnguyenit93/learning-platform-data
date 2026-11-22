# Feature đã final và feature preview trong Java Pattern Matching

Trong Java, một tính năng ngôn ngữ có thể xuất hiện lần đầu ở trạng thái **preview** (thử nghiệm có kiểm soát), được điều chỉnh qua nhiều bản JDK, rồi mới trở thành **final** (tính năng chính thức của Java SE). Điều này đặc biệt quan trọng với **pattern matching**, bởi cùng một ý tưởng đã trải qua nhiều mốc phát hành: type pattern trong `instanceof`, record patterns và pattern matching cho `switch` **không final cùng một phiên bản**.

Bài này giúp phân biệt trạng thái tính năng, chọn đúng JDK, sử dụng `--release` và `--enable-preview` đúng cách, đọc lỗi biên dịch/chạy và lập kế hoạch chuyển mã từ preview sang final. Trọng tâm là Java Core Pattern Matching, không phải mọi tính năng Java trong các bản phát hành.

**Điểm cần nhớ:** Với các tính năng chính được giải thích ở đây, `instanceof` type pattern đã final từ **Java 16**, còn **record patterns** và **pattern matching cho `switch` final từ Java 21**. Mã Java 21 ở phần thực hành chạy **không cần** `--enable-preview`.

## 1. Preview, final và incubator khác nhau thế nào?

### Feature preview

Một **preview language feature** đã có thiết kế và implementation thực tế, được đưa vào một bản JDK để cộng đồng dùng thử và phản hồi, nhưng **chưa trở thành phần chính thức ổn định của ngôn ngữ Java SE trong bản đó**. Preview có thể thay đổi cú pháp, ngữ nghĩa hoặc phạm vi hỗ trợ khi chuyển sang bản preview tiếp theo.

Khi thực sự dùng cú pháp preview, cần chủ động bật preview lúc **biên dịch** và **chạy**:

```bash
# Minh họa cho một feature đang là preview ở JDK N, với đúng JDK N.
javac --enable-preview --release N Example.java
java --enable-preview Example
```

`N` ở đây là **ký hiệu cho số phiên bản của đúng JDK đang dùng** (ví dụ `17` khi chạy `javac` của JDK 17), không phải nguyên văn một lệnh có thể sao chép với chữ `N`. Các lệnh cụ thể cho Java 17 nằm ở mục 6.

Điểm quan trọng: `--enable-preview` không có nghĩa “bật mọi tính năng tương lai” hoặc “cho phép dùng bất kỳ preview ở bất kỳ bản JDK cũ nào”. Nó chỉ mở các tính năng preview của **đúng phiên bản nguồn mà compiler hiện tại hỗ trợ**.

### Feature final

Khi feature trở thành **final**, cú pháp/ngữ nghĩa của tính năng đó được đưa vào đặc tả Java SE tương ứng. Người học và ứng dụng có thể sử dụng nó theo cấu hình biên dịch bình thường của phiên bản đã hỗ trợ, ví dụ:

```bash
# Với JDK 21 hoặc compiler mới hơn hỗ trợ --release 21:
javac --release 21 Example.java
java Example
```

Không cần `--enable-preview` nếu `Example.java` chỉ dùng những tính năng đã final ở Java 21 hoặc cũ hơn. Điều này **không** có nghĩa mọi đoạn code viết bằng preview cũ tự động biên dịch với cú pháp final mới: các đợt preview có thể đổi cú pháp và quy tắc.

### Incubator không đồng nghĩa preview

Java còn có **incubator modules/APIs**. Chúng có thể cần các module đặc biệt và cấu hình `--add-modules`. Đó là cơ chế khác với **preview language features** và cờ `--enable-preview`. Đừng gọi một API incubator là “pattern matching preview” chỉ vì nó cũng chưa được ổn định.

Trong bài này, “preview” chỉ các **ngữ pháp/cơ chế ngôn ngữ** liên quan đến pattern matching, không phải trạng thái mọi thư viện Java.

## 2. Dòng thời gian chuẩn hóa các tính năng Pattern Matching

Mỗi mốc dưới đây chỉ trạng thái của **tính năng cụ thể** trong bản Java đó, không phải trạng thái chung của toàn bộ ngôn ngữ.

| Tính năng | Các bản preview | Bản final | JEP final |
| --- | --- | --- | --- |
| Pattern matching cho `instanceof` | Java 14 (JEP 305), Java 15 (JEP 375) | **Java 16** | [JEP 394](https://openjdk.org/jeps/394) |
| Record patterns / deconstruction | Java 19 (JEP 405), Java 20 (JEP 432) | **Java 21** | [JEP 440](https://openjdk.org/jeps/440) |
| Pattern matching cho `switch` | Java 17 (JEP 406), 18 (JEP 420), 19 (JEP 427), 20 (JEP 433) | **Java 21** | [JEP 441](https://openjdk.org/jeps/441) |

### Vì sao có nhiều lần preview?

Tính năng có thể được thử nghiệm qua nhiều bản JDK để điều chỉnh cách đặt biến, phạm vi biến (*flow scoping*), xử lý `null`, guard, dominance và tính *exhaustive* của `switch`. Bởi vậy mã preview viết ở một bản JDK **không được bảo đảm tương thích nguồn** với bản preview kế tiếp hoặc với cú pháp final.

Một ví dụ quan trọng: các vòng thiết kế pattern matching cho `switch` đã có thay đổi về cách biểu diễn **guard** trước khi cú pháp `when` trở thành một phần của tính năng final ở Java 21. Do đó không nên lấy mã `case String s when ...` trong bài Java 21 rồi giả định nó biên dịch nguyên dạng ở mọi bản preview trước đó.

### Các tính năng nền tảng có lịch sử riêng

Pattern matching thường được đặt trên domain model `record` và `sealed`, nhưng hai tính năng này có lịch sử chuẩn hóa riêng:

| Tính năng nền tảng | Preview | Final |
| --- | --- | --- |
| `record` | Java 14 (JEP 359), Java 15 (JEP 384) | **Java 16**, JEP 395 |
| `sealed class` / `sealed interface` | Java 15 (JEP 360), Java 16 (JEP 397) | **Java 17**, JEP 409 |

**Không nhầm `record` với `record pattern`:** Java 17 đã có thể khai báo `record Point(int x, int y) {}`, nhưng cú pháp **deconstruct** `case Point(int x, int y) -> ...` chưa phải tính năng final ở Java 17. Record patterns final từ Java 21.

## 3. Chọn phiên bản Java theo đúng cú pháp

Xét các đoạn mẫu sau:

### Type pattern trong instanceof

```java
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
```

`String text` là **type pattern** của `instanceof`, đã final từ **Java 16**. Trong Java 17 hoặc Java 21, cú pháp này dùng được không cần preview flag.

### Khai báo record

```java
record Point(int x, int y) {}
```

`record` đã final từ **Java 16**. Dòng này một mình không cần record pattern và không cần preview trên Java 17+.

### Record pattern trong instanceof

```java
Object input = new Point(2, 3);
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

`Point(int x, int y)` là **record pattern**, tách trực tiếp hai component. Đây là cú pháp final từ **Java 21**; nếu dự án đặt `--release 17`, việc dùng record pattern không hợp lệ với mức ngôn ngữ đó.

### Pattern switch

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text=" + text;
        case Integer number -> "number=" + number;
        default -> "other";
    };
}
```

Đây là **pattern matching cho switch**, final từ **Java 21**. Tính năng từng tồn tại dưới dạng preview ở Java 17–20. Khi biên dịch `--release 21` trên JDK hỗ trợ, không cần `--enable-preview`.

**Quy tắc chọn tối thiểu:**

- Chỉ cần `instanceof Type variable`: có thể chọn Java **16+**.
- Dùng `record` và `sealed`, nhưng không dùng record patterns/pattern switch: Java **17+** hỗ trợ các phần này ở trạng thái final.
- Dùng record patterns hoặc pattern switch ở trạng thái final: chọn **Java 21+**.
- Nếu dự án đang giữ một JDK cũ và tính năng chỉ là preview trong đúng JDK đó, cần cả cấu hình compile/runtime thích hợp; phải chấp nhận rủi ro thay đổi giữa các bản preview.

Các mốc trên là **mức tối thiểu theo cú pháp ngôn ngữ**. Một chương trình còn có thể phụ thuộc các API, thư viện và chính sách runtime khác.

## 4. Java 17: ví dụ chỉ dùng feature đã final

Ví dụ này chỉ dùng `record` và pattern matching cho `instanceof`, **không** dùng pattern switch hay record deconstruction. Lưu thành tệp **`FinalSeventeenDemo.java`**:

```java
public class FinalSeventeenDemo {
    record Account(String code) {}

    static String label(Object input) {
        if (input instanceof Account a && a.code() != null) {
            return "ACCOUNT=" + a.code();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(label(new Account("A01")));
        System.out.println(label(new Account(null)));
        System.out.println(label(null));
    }
}
```

Biên dịch theo Java 17:

```bash
javac --release 17 -encoding UTF-8 FinalSeventeenDemo.java
java FinalSeventeenDemo
```

**Stdout chính xác:**

```text
ACCOUNT=A01
OTHER
OTHER
```

Điều gì được kiểm tra?

1. `Account` là một record **final** trong Java 17.
2. `input instanceof Account a` là type pattern **final** từ Java 16.
3. `a.code() != null` được đánh giá sau khi `instanceof` thành công nhờ `&&` short-circuit; nếu `input == null`, điều kiện đầu trả false.
4. Record có thể giữ thành phần tham chiếu `null` nếu constructor không cấm; đó là lý do `a.code() != null` vẫn có ý nghĩa.

Chương trình đã được biên dịch bằng `javac --release 17` và thực thi thành công trên một JDK mới hơn có khả năng chạy bytecode Java 17.

## 5. Java 21: record patterns và pattern switch đã final

Lưu chương trình sau thành **`FinalPatternCompatibilityDemo.java`**. Nó kết hợp `sealed interface`, các record, record patterns, type/component patterns, guard `when`, `case null` và một phép `instanceof`.

```java
public class FinalPatternCompatibilityDemo {
    sealed interface Event permits Text, Amount, Pair {}
    record Text(String value) implements Event {}
    record Amount(int cents) implements Event {}
    record Pair(Event first, Event second) implements Event {}

    static String describe(Event input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Text(var value) when value == null -> "TEXT_NULL";
            case Text(var value) when value.isBlank() -> "TEXT_BLANK";
            case Text(String value) -> "TEXT=" + value;
            case Amount(int cents) when cents < 0 -> "NEGATIVE=" + cents;
            case Amount(var cents) -> "AMOUNT=" + cents;
            case Pair(Text(var text), Amount(var cents)) ->
                    "PAIR=" + text + ":" + cents;
            case Pair(var first, var second) -> "OTHER_PAIR";
        };
    }

    static String describeIf(Object input) {
        if (input instanceof Text(var text)
                && text != null
                && !text.isBlank()) {
            return "IF=" + text;
        }
        return "IF_OTHER";
    }

    public static void main(String[] args) {
        System.out.println("null=" + describe(null));
        System.out.println("missing=" + describe(new Text(null)));
        System.out.println("blank=" + describe(new Text("  ")));
        System.out.println("text=" + describe(new Text("Java")));
        System.out.println("negative=" + describe(new Amount(-1)));
        System.out.println("zero=" + describe(new Amount(0)));
        System.out.println("nested=" + describe(
                new Pair(new Text("A"), new Amount(3))));
        System.out.println("other-pair=" + describe(
                new Pair(null, new Amount(3))));
        System.out.println(describeIf(new Text("Ready")));
        System.out.println(describeIf(new Text(null)));
    }
}
```

Chạy bằng JDK có hỗ trợ Java 21:

```bash
javac --release 21 -encoding UTF-8 FinalPatternCompatibilityDemo.java
java FinalPatternCompatibilityDemo
```

**Không có cờ `--enable-preview` trong cả hai lệnh.**

**Stdout chính xác:**

```text
null=NULL_SELECTOR
missing=TEXT_NULL
blank=TEXT_BLANK
text=TEXT=Java
negative=NEGATIVE=-1
zero=AMOUNT=0
nested=PAIR=A:3
other-pair=OTHER_PAIR
IF=Ready
IF_OTHER
```

Giải thích liên hệ với trạng thái final:

- `case Text(var value)` và `case Pair(Text(var text), Amount(var cents))` dùng **record patterns**, final từ Java 21.
- `case ... when ...` dùng **guard của pattern switch**, nằm trong tính năng final Java 21.
- `case null` là cách xử lý selector null rõ ràng; nếu switch chỉ có các pattern không xử lý null, selector null có thể gây `NullPointerException`.
- `Text(var value)` có thể ràng buộc component `null`, vì `var` là component pattern không điều kiện đối với kiểu khai báo. Vì thế case `value == null` phải đi trước `value.isBlank()` để tránh NPE.
- `Pair(Text(...), Amount(...))` chỉ khớp khi hai record con cần tách tồn tại và đúng kiểu. `Pair(null, new Amount(3))` rơi vào `Pair(var first, var second)` và trả `OTHER_PAIR`.
- `sealed Event` cùng ba subtype `final` làm cho `switch expression` có thể exhaustive với các trường hợp đang định nghĩa, không cần `default` che subtype mới.
- `describeIf` cho thấy `instanceof` và `&&` vẫn áp dụng flow scoping với record pattern sau Java 21.

Chương trình trên đã được kiểm chứng bằng `javac --release 21` và chạy thành công với đúng mười dòng output.

## 6. Minh họa lịch sử: pattern switch còn preview ở Java 17

Để thấy khác biệt, xét **Java 17**, khi pattern matching cho `switch` **chưa final**. Mẫu sau chỉ dùng type patterns ở `case`, không dùng record patterns. Lưu dưới tên **`PreviewSwitch17.java`** nếu muốn chạy trong môi trường đúng **JDK 17**:

```java
public class PreviewSwitch17 {
    static String label(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text -> "string=" + text;
            case Integer number -> "integer=" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label(7));
        System.out.println(label(null));
    }
}
```

Trong **JDK 17**, dùng:

```bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview PreviewSwitch17
```

**Đầu ra kỳ vọng trên JDK 17 phù hợp:**

```text
string=Java
integer=7
missing
```

Đây là **ví dụ tương thích lịch sử cho cú pháp preview Java 17**; nó không được thực thi trong đợt kiểm chứng hiện tại vì môi trường dùng compiler JDK 24, không có compiler JDK 17. Phần ví dụ Java 17 đã **final** ở mục 4 và Java 21 đã **final** ở mục 5 mới là hai chương trình được biên dịch/chạy thực tế.

Nếu quên `--enable-preview` khi biên dịch bằng JDK 17, compiler có thể báo rằng pattern trong switch là preview feature và preview chưa được bật. Nếu đã biên dịch **thật sự sử dụng** preview nhưng quên cờ lúc chạy, JVM có thể từ chối tải lớp vì preview chưa được bật.

**Không lấy đoạn `PreviewSwitch17.java` rồi tự thêm record pattern Java 21** để kỳ vọng nó chạy trên JDK 17. Tính năng record pattern chưa được hỗ trợ ở bản đó, kể cả khi đã bật preview.

## 7. Vì sao bật preview nhưng vẫn bị lỗi?

### --enable-preview bị ràng buộc với phiên bản nguồn hiện tại

Cờ `--enable-preview` không phải “cờ tương thích ngược cho mọi bản preview trước”. Với compiler ở một bản Java mới, `--enable-preview` chỉ áp dụng preview của **phiên bản nguồn mà compiler đó hỗ trợ để thử nghiệm**.

Ví dụ đã được kiểm chứng bằng **`javac 24.0.2`**:

```bash
javac --enable-preview --release 21 FinalPatternCompatibilityDemo.java
```

Compiler JDK 24 từ chối với thông điệp trọng tâm:

```text
error: invalid source release 21 with --enable-preview
  (preview language features are only supported for release 24)
```

Lý do: `--release 21` yêu cầu mức nguồn Java 21, còn `--enable-preview` trên compiler đó chỉ bật preview theo mức 24. **Đây là lỗi tổ hợp tùy chọn**, không có nghĩa record patterns hoặc pattern switch vẫn preview ở Java 21.

Để biên dịch tính năng **đã final** trong Java 21 bằng JDK 24, dùng:

```bash
javac --release 21 FinalPatternCompatibilityDemo.java
```

Còn nếu thật sự cần một preview feature của JDK 24, phải dùng cấu hình preview **ứng với JDK 24**, và cả môi trường runtime tương ứng — không được hạ `--release` xuống 21 để cố gắng dùng cú pháp preview mới.

### Runtime của lớp preview cũng có yêu cầu phiên bản

Với một **class file có đánh dấu preview** (sử dụng preview feature), JVM phải được bật preview và có phiên bản feature tương ứng. Không nên giả định bytecode preview của một JDK cũ sẽ chạy được trên mọi JDK mới như một class final thông thường. Preview class files dùng **class-file minor version đặc biệt `65535`** để JVM có thể phân biệt.

Vì vậy, ở dự án dùng preview, kiểm tra **cả javac và java thực tế đang được gọi**, không chỉ giá trị cấu hình Maven/Gradle.

```bash
java -version
javac -version
```

Hãy đảm bảo hai công cụ thuộc cùng JDK phù hợp với tính năng preview đang dùng. Đổi máy hoặc nâng CI image có thể làm một lệnh preview lịch sử không còn hợp lệ.

## 8. --release, --source, --target và runtime: không nên đánh đồng

Các tùy chọn có mục đích khác nhau:

| Tùy chọn / công cụ | Vai trò chính | Lưu ý |
| --- | --- | --- |
| `javac --release N` | Biên dịch với quy tắc ngôn ngữ, class-file target và API nền tảng của Java `N` khi compiler hỗ trợ | Phù hợp để xây dựng artifact chạy trên Java `N` |
| `javac --source N` | Chọn mức cú pháp/ngữ nghĩa nguồn | Dùng riêng không bảo đảm bị giới hạn về API của Java `N` |
| `javac --target N` | Chọn phiên bản class file | Không tự hạ cấp cú pháp/API hay thay thế `--release` |
| `javac --enable-preview` | Bật preview của phiên bản compiler/source được phép | Dùng đúng phiên bản, không bật lại mọi preview trong lịch sử |
| `java --enable-preview` | Cho JVM chạy class cần preview với bản phù hợp | Không thay thế flag lúc biên dịch |
| `java -version` | Hiện bản JVM thực tế dùng để chạy | Có thể khác `javac -version` nếu PATH/JAVA_HOME cấu hình lệch |

**Ví dụ tương thích nguồn:** JDK 24 có thể dùng `javac --release 17` để biên dịch chương trình mục 4, và `javac --release 21` để biên dịch chương trình mục 5. Điều đó **không** làm những tính năng Java 21 trở thành hợp lệ nếu đặt `--release 17`.

**Ví dụ tương thích runtime:** class file được build bằng target Java 21 thông thường cần runtime hỗ trợ class-file version của Java 21 trở lên. Nếu cố chạy bằng một JDK cũ hơn, thường gặp `UnsupportedClassVersionError`. Bật `--enable-preview` không giải quyết được tình trạng runtime quá cũ cho class-file version đó.

**Khuyến nghị:** Với thư viện/app triển khai cho Java 17, build và test bằng `--release 17`. Nếu muốn dùng pattern switch final, kế hoạch nâng mức tối thiểu lên Java 21 phải được đánh giá cùng runtime CI/production và dependency, không chỉ đổi một flag.

## 9. Migration: từ mã preview sang mã final

Giả sử một dự án đã dùng pattern switch preview trên JDK 17, 18, 19 hoặc 20. Khi nâng lên Java 21, thực hiện theo quy trình:

1. **Xác định bản preview xuất phát.** Đọc `pom.xml`/`build.gradle` trong dự án thực tế và bản JDK toolchain, nhưng đồng thời kiểm tra cú pháp source. Bản JDK đang cài chưa chắc là mức ngôn ngữ build.
2. **Tra JEP của chính bản đó.** Thay đổi giữa các vòng preview có thể ảnh hưởng guard, loại pattern được hỗ trợ, scope của biến, thứ tự label, xử lý null hoặc exhaustiveness.
3. **Sửa nguồn sang cú pháp final Java 21.** Với switch, xem lại các nhánh `case`, cú pháp guard `when`, `case null` và thứ tự case hẹp → rộng. Với record pattern, xem lại deconstruction và component null.
4. **Đặt compiler release thành 21** rồi biên dịch **không preview** để chắc chắn không còn phụ thuộc tính năng preview cũ:
   `javac --release 21 ...`.
5. **Sửa lỗi biên dịch thực chất** như dominated case hoặc switch expression không exhaustive. Đừng chỉ thêm `default` rộng để che subtype mới trong sealed hierarchy.
6. **Cập nhật cả test và packaging.** Nếu trước đó cấu hình `--enable-preview` cho compile, test, chạy ứng dụng hoặc IDE, kiểm tra từng nơi và gỡ cờ khi không còn dùng preview. Nếu dự án vẫn dùng một **feature khác còn preview** ở JDK mục tiêu, không được gỡ mù quáng.
7. **Chạy regression tests** với selector null, type pattern, subtype, guard true/false, record component null và các giá trị biên. Cú pháp mới có thể biên dịch nhưng nhánh nghiệp vụ vẫn thay đổi nếu bạn sắp lại case.
8. **Kiểm tra runtime production.** Đừng biên dịch `--release 21` rồi triển khai trên runtime Java 17. Đảm bảo CI, container, server và môi trường người dùng có Java 21 hoặc mới hơn theo yêu cầu ứng dụng.

### Trường hợp dự án chưa thể nâng khỏi Java 17

Không nên ép **record pattern** hoặc **pattern switch final** vào source Java 17. Bạn vẫn có thể áp dụng **type pattern trong `instanceof`** (đã final), `record` và `sealed` (đều final ở Java 17), rồi dùng `if/else if` hoặc Visitor để phân loại dữ liệu. Đây là đường thiết kế ổn định khi điều kiện triển khai yêu cầu Java 17.

## 10. Tình huống thường gặp trong build tool và CI

### Trên IDE chạy được nhưng CI lỗi

Kiểm tra ba thông số:

- **JDK dùng để compile**: `javac -version` trong CI.
- **Mức ngôn ngữ**: `--release`/source compatibility từ cấu hình build.
- **Runtime dùng khi test và chạy**: `java -version`, các tham số JVM, toolchain của IDE/build tool.

Ví dụ: máy phát triển có JDK 24, source dùng record pattern nhưng CI build với `--release 17`. Mã hợp lệ ở ngôn ngữ Java 21 vẫn không hợp lệ ở mức nguồn Java 17. Hạ lỗi này xuống “chỉ thiếu `--enable-preview`” là chẩn đoán sai.

### Với Maven/Gradle

Nếu thật sự dùng preview của một JDK, cần cấu hình preview **tại compiler và tại JVM của các task chạy/test**, đồng thời khóa toolchain JDK phù hợp. Cách khai báo tùy plugin phiên bản Maven/Gradle và pipeline; không được giả định bật một thuộc tính source compatibility là đủ.

Nếu dùng **pattern matching final của Java 21**, cấu hình nên tập trung vào **toolchain Java 21+ và `--release 21`**, không cần preview flag chỉ vì cú pháp có pattern.

### Thư viện phân phối cho nhiều nhóm sử dụng

Xác định **minimum supported Java version** trong tài liệu sản phẩm. Tránh xuất bản artifact chứa bytecode hoặc API của Java 21 nếu thư viện cam kết còn chạy trên Java 17. Tách module, cung cấp phiên bản khác hoặc hoãn sử dụng cú pháp mới nếu cần giữ runtime thấp.

Preview nên được thử nghiệm có kiểm soát, không mặc nhiên coi là API/source contract đã ổn định cho toàn bộ người dùng thư viện.

## 11. Bảng lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hành động phù hợp |
| --- | --- | --- |
| Compiler báo pattern switch là preview feature | Biên dịch source có switch pattern trên bản Java mà nó còn preview, chưa bật preview | Chọn đúng JDK và cờ `--enable-preview` cho bản đó, hoặc nâng lên Java 21 final |
| `invalid source release N with --enable-preview` | Cố bật preview của release không phải release preview được compiler hiện tại hỗ trợ | Bỏ cờ nếu feature đã final ở `N`; nếu cần preview thật, đổi toolchain/release phù hợp |
| `UnsupportedClassVersionError` khi chạy | Runtime quá cũ để đọc class-file version đã build | Chạy với JDK đủ mới hoặc build lại ở target được hỗ trợ |
| JVM báo preview features chưa enabled | Chạy class được biên dịch với preview mà thiếu flag runtime | Dùng đúng JDK và `java --enable-preview` |
| Cú pháp `Point(var x, var y)` không biên dịch ở `--release 17` | Record pattern chưa phải tính năng Java 17 | Dùng Java 21+ hoặc viết accessor/type pattern tương thích Java 17 |
| Cú pháp `when` không chạy trong code preview cũ | Cú pháp/semantics preview đã thay đổi giữa các JDK | Đọc JEP của bản nguồn, cập nhật code khi nâng phiên bản |
| `this case label is dominated by a preceding case label` | Nhánh rộng che nhánh cụ thể, vi phạm dominance | Đặt nhánh cụ thể/guard phù hợp trước nhánh rộng |
| Switch expression không exhaustive | Thiếu nhánh bao phủ kiểu selector (đặc biệt khi sealed hierarchy thay đổi) | Bổ sung case có ý nghĩa, không dùng default để né kiểm tra một cách máy móc |
| `NullPointerException` trong switch | Selector null chưa có `case null`, hoặc component pattern mang null bị dereference | Phân biệt hai cấp null, đặt case/guard đúng |
| Mã chạy ở IDE nhưng fail trên CI | JDK, `--release` hoặc tham số preview/test giữa các môi trường khác nhau | Kiểm tra toolchain thực tế và khóa cấu hình |

**Lưu ý về lời báo lỗi:** diagnostic cụ thể phụ thuộc JDK và phiên bản nguồn. Đọc thông điệp cùng dòng source, version compiler và flags; đừng lấy duy nhất câu chữ lỗi của một bản JDK làm quy tắc chung.

## 12. Kiểm thử tương thích bằng bảng nhỏ

Một bài kiểm tra tương thích hữu ích:

| Nguồn Java | Mức biên dịch | Kỳ vọng |
| --- | --- | --- |
| `FinalSeventeenDemo.java` (mục 4) | `--release 17` với compiler hỗ trợ | **Biên dịch được**, không preview |
| `FinalPatternCompatibilityDemo.java` (mục 5) | `--release 21` với compiler hỗ trợ | **Biên dịch được**, không preview |
| Nguồn Java 21 dùng record patterns | `--release 17` | **Không hợp lệ** theo Java 17 |
| Preview switch Java 17 (mục 6) | `--enable-preview --release 17` trên JDK 17 | Có thể biên dịch/chạy preview với cờ cả hai pha |
| Bật `--enable-preview --release 21` trên compiler JDK 24 | JDK 24 | **Lỗi tổ hợp flag** do preview chỉ hỗ trợ mức 24 của compiler |

Hai dòng **final** đã được biên dịch và chạy thực tế với `javac 24.0.2` bằng `--release 17` và `--release 21` tương ứng. Tình huống mismatch `--enable-preview --release 21` cũng đã được kiểm chứng trên compiler đó. Dòng preview JDK 17 là hướng dẫn lịch sử từ thiết kế tính năng, không được thực thi trong môi trường JDK 24 hiện có.

Khi làm việc nhóm, nên tự động hóa một **compatibility matrix trong CI**: ít nhất compile theo release cam kết, chạy test trên runtime tối thiểu, và kiểm tra thêm một JDK mới hơn nếu hệ thống có yêu cầu hỗ trợ.

## 13. Những sai lầm phổ biến

1. **Nghĩ mọi pattern matching đều preview.** `instanceof` type pattern final Java 16; record patterns và switch pattern final Java 21.
2. **Nghĩ record và record pattern là một tính năng.** Khai báo `record` final Java 16, nhưng tách record bằng pattern final Java 21.
3. **Dùng `--enable-preview` để “nâng cấp” Java 17 thành Java 21.** Cờ này không mở những tính năng không tồn tại trong JDK 17.
4. **Bật preview theo `--release` cũ trên compiler mới.** Preview flag phải hợp với source/release mà compiler đó cho phép; mismatch là lỗi biên dịch.
5. **Chỉ bật preview lúc compile.** Mã thực sự dùng preview có thể cần flag runtime `java --enable-preview` với JDK phù hợp.
6. **Giả định preview source ổn định qua các bản.** Cú pháp guard và các quy tắc pattern switch đã có những vòng điều chỉnh; khi nâng JDK cần rà soát.
7. **Gỡ preview flag mà không xem feature khác còn preview.** Dự án có thể dùng nhiều tính năng khác nhau với trạng thái riêng.
8. **Đọc JDK version từ IDE thay cho compiler CI.** PATH, JAVA_HOME, Maven/Gradle toolchain và runtime thực tế có thể không trùng.
9. **Nhầm version class file với version source.** `--source` và `--target` riêng lẻ không tương đương `--release`.
10. **Cho rằng code final ở Java 21 cũng hợp lệ ở Java 17.** Final chỉ có hiệu lực từ đúng bản chuẩn hóa tính năng đó trở đi.
11. **Cho rằng `default` bao phủ null.** Pattern switch có chính sách selector null riêng; cần `case null` hoặc guard trước switch nếu nghiệp vụ yêu cầu.
12. **Thêm `default` để tránh exhaustive case.** Có thể che lỗi khi thêm subtype `sealed` mới. Cần kiểm tra ý nghĩa domain.
13. **Đưa mã preview lịch sử vào thư viện production mà không khóa toolchain.** Điều đó tạo rủi ro tương thích khi chuyển môi trường triển khai.
14. **Chỉ kiểm thử happy path khi migrate preview → final.** Thử cả null selector, record component null, guard true/false, subtype và case bị dominated.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Project đang target Java 17. Có thể dùng `if (input instanceof String text)` không? Có cần `--enable-preview` không?

*Đáp án:* Có thể dùng; type pattern cho `instanceof` đã final từ Java 16. Với Java 17 không cần preview flag cho tính năng này.

**Câu 2.** Project dùng Java 17 và đã khai báo `record Point(int x, int y) {}`. Có thể dùng `case Point(int x, int y) -> ...` như tính năng final không?

*Đáp án:* Không. `record` final Java 16, còn record pattern final Java 21. Cần nâng mức ngôn ngữ lên Java 21 hoặc chuyển sang cách xử lý khác phù hợp Java 17.

**Câu 3.** Dùng JDK 24 và chạy `javac --enable-preview --release 21`. Tại sao bị lỗi dù pattern switch đã final ở Java 21?

*Đáp án:* Preview flag của compiler JDK 24 không dùng cho `--release 21`. Vì pattern switch đã final, nếu source chỉ dùng tính năng đã final của Java 21 thì hãy **bỏ `--enable-preview`** và biên dịch bằng `--release 21`.

**Câu 4.** Khi chạy class sử dụng preview feature của JDK 17, chỉ bật `--enable-preview` khi biên dịch đã đủ chưa?

*Đáp án:* Chưa. Cần chạy bằng JDK tương ứng với preview và bật `java --enable-preview` để JVM cho phép lớp có đánh dấu preview; nếu không, lớp có thể bị từ chối.

**Câu 5.** Vì sao không thể chắc chắn mã preview Java 17 sẽ chạy nguyên dạng trên Java 21 sau khi bỏ cờ preview?

*Đáp án:* Vì preview có thể thay đổi cú pháp/ngữ nghĩa qua nhiều JEP. Cần cập nhật nguồn theo đặc tả final Java 21 và chạy bộ regression test.

**Câu 6.** Nếu API thư viện cam kết chạy trên Java 17 nhưng bạn muốn dùng record patterns Java 21, cần quyết định điều gì trước?

*Đáp án:* Phải lựa chọn nâng **minimum runtime/source version** (và cập nhật cam kết hỗ trợ), hoặc giữ Java 17 và dùng cách triển khai phù hợp; không thể giữ `--release 17` rồi sử dụng record patterns final Java 21 như một tính năng đã có của Java 17.

## 15. Tài liệu chính thức

- [JEP 305 – Pattern Matching for instanceof (Preview, Java 14)](https://openjdk.org/jeps/305)
- [JEP 375 – Pattern Matching for instanceof (Second Preview, Java 15)](https://openjdk.org/jeps/375)
- [JEP 394 – Pattern Matching for instanceof (Final, Java 16)](https://openjdk.org/jeps/394)
- [JEP 405 – Record Patterns (Preview, Java 19)](https://openjdk.org/jeps/405)
- [JEP 432 – Record Patterns (Second Preview, Java 20)](https://openjdk.org/jeps/432)
- [JEP 440 – Record Patterns (Final, Java 21)](https://openjdk.org/jeps/440)
- [JEP 406 – Pattern Matching for switch (Preview, Java 17)](https://openjdk.org/jeps/406)
- [JEP 420 – Pattern Matching for switch (Second Preview, Java 18)](https://openjdk.org/jeps/420)
- [JEP 427 – Pattern Matching for switch (Third Preview, Java 19)](https://openjdk.org/jeps/427)
- [JEP 433 – Pattern Matching for switch (Fourth Preview, Java 20)](https://openjdk.org/jeps/433)
- [JEP 441 – Pattern Matching for switch (Final, Java 21)](https://openjdk.org/jeps/441)
- [JEP 12 – Preview Features (quy trình bật và dùng preview)](https://openjdk.org/jeps/12)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification 21 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
