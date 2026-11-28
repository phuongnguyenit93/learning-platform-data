# Tùy biến equals và hashCode nhất quán khi nghiệp vụ yêu cầu

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record tự sinh `equals(Object)` và `hashCode()` dựa trên các component. Với phần lớn record dùng làm value object hoặc khóa dữ liệu, cặp phương thức mặc định đã phù hợp và nên được giữ nguyên. Tuy nhiên, một số miền nghiệp vụ định nghĩa hai giá trị là tương đương theo quy tắc riêng, khác với `equals` của kiểu component.

Khi đó có thể khai báo tường minh cả `equals` và `hashCode` trong record. Điều quan trọng là hai phương thức phải thể hiện **cùng một quy tắc equality**, tuân thủ hợp đồng của `Object` và giữ copy invariant của record. Bài học dùng `BigDecimal` làm ví dụ: có trường hợp nghiệp vụ muốn xem `1.0` và `1.00` là cùng một giá trị số, dù `BigDecimal.equals` xem chúng khác nhau vì scale khác nhau.

## 1. Khi nào nên giữ equals và hashCode mặc định?

Với khai báo:

```java
record UserKey(String tenantId, String username) {}
```

Record tự sinh equality từ lớp record và các component. Hai instance cùng lớp và có các component bằng nhau sẽ được xem là bằng nhau:

```java
UserKey first = new UserKey("acme", "linh");
UserKey second = new UserKey("acme", "linh");

System.out.println(first == second);      // false: hai instance
System.out.println(first.equals(second)); // true: cùng giá trị
```

Đây là lựa chọn phù hợp khi ý nghĩa nghiệp vụ đúng là: mọi component đều tham gia xác định giá trị và cách so sánh mặc định của từng component đã đúng.

Không nên ghi đè phương thức chỉ để thay đổi cách in, tăng hiệu năng theo cảm tính hoặc làm kết quả trông thuận tiện hơn. Custom equality làm thay đổi cách record hoạt động trong `Map`, `Set` và mọi API dựa trên `equals`; chỉ thực hiện khi có một quy tắc nghiệp vụ cụ thể cần thể hiện.

## 2. Ví dụ nghiệp vụ: so sánh BigDecimal bỏ qua scale

`BigDecimal` biểu diễn số thập phân bằng một giá trị nguyên chưa scale (*unscaled value*) cùng với scale. `equals` yêu cầu cả giá trị số lẫn scale tương ứng, trong khi `compareTo` so sánh giá trị số và có thể trả về `0` cho hai số khác scale:

```java
import java.math.BigDecimal;

BigDecimal oneDecimal = new BigDecimal("1.0");
BigDecimal twoDecimals = new BigDecimal("1.00");

System.out.println(oneDecimal.equals(twoDecimals)); // false
System.out.println(oneDecimal.compareTo(twoDecimals) == 0); // true
```

Giả sử một miền nghiệp vụ định nghĩa `DecimalValue` là một giá trị số, không coi scale là một phần của identity. Khi đó hai component `BigDecimal` có thể được xem là bằng nhau nếu `compareTo` trả về `0`.

Chỉ áp dụng quy tắc này khi scale thực sự không mang ý nghĩa nghiệp vụ. Với tiền tệ, độ chính xác, số chữ số thập phân và quy tắc làm tròn có thể quan trọng; không tự động bỏ qua scale nếu hợp đồng dữ liệu yêu cầu phân biệt chúng.

## 3. Triển khai cả equals và hashCode

Ví dụ:

```java
import java.math.BigDecimal;
import java.util.Objects;

record DecimalValue(BigDecimal value) {
    DecimalValue {
        value = Objects.requireNonNull(value, "value");
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof DecimalValue that
                && value.compareTo(that.value) == 0);
    }

    @Override
    public int hashCode() {
        return value.stripTrailingZeros().hashCode();
    }
}
```

Hai phương thức dùng cùng một quy tắc:

- `equals` xem hai `BigDecimal` bằng nhau khi `compareTo` trả về `0`, tức là cùng giá trị số dù scale khác nhau.
- `hashCode` chuẩn hóa scale bằng `stripTrailingZeros()` trước khi tính hash. Các số bằng nhau theo quy tắc `compareTo` vì vậy có cùng mã băm.

Kiểm tra:

```java
DecimalValue first = new DecimalValue(new BigDecimal("1.0"));
DecimalValue second = new DecimalValue(new BigDecimal("1.00"));
DecimalValue third = new DecimalValue(new BigDecimal("1.000"));

System.out.println(first.equals(second)); // true
System.out.println(second.equals(third)); // true
System.out.println(first.equals(third));  // true

System.out.println(first.hashCode() == second.hashCode()); // true
System.out.println(second.hashCode() == third.hashCode()); // true
```

`BigDecimal` là immutable, nên component không thay đổi sau khi tạo record. Điều này cũng giúp `hashCode` ổn định khi record được dùng làm khóa.

## 4. Hợp đồng bắt buộc của equals

Khi ghi đè `equals(Object)`, implementation phải giữ các tính chất của hợp đồng `Object.equals`:

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ (*reflexive*) | Với mọi tham chiếu khác `null`, `x.equals(x)` phải là `true`. |
| Đối xứng (*symmetric*) | `x.equals(y)` là `true` khi và chỉ khi `y.equals(x)` là `true`. |
| Bắc cầu (*transitive*) | Nếu `x.equals(y)` và `y.equals(z)` là `true` thì `x.equals(z)` cũng phải là `true`. |
| Nhất quán (*consistent*) | Nếu thông tin dùng trong so sánh không đổi, gọi lại `equals` phải cho cùng kết quả. |
| Khác null | Với mọi `x` khác null, `x.equals(null)` phải là `false`. |

Ví dụ `DecimalValue` giữ các tính chất này vì `BigDecimal.compareTo` xác định một quan hệ tương đương theo giá trị số. Việc kiểm tra `this == other` ở đầu phương thức xử lý trường hợp một instance được so sánh với chính nó.

Record class là class ngầm định `final`, nên không có lớp con mở rộng record để tạo ra bất đối xứng equality qua kế thừa. Dù vậy, vẫn phải kiểm tra đúng kiểu và không so sánh tùy tiện với object khác lớp.

## 5. Hợp đồng bắt buộc của hashCode

`hashCode` phải nhất quán với `equals`:

- Nếu `a.equals(b)` là `true` thì `a.hashCode()` và `b.hashCode()` bắt buộc bằng nhau.
- Hai object có cùng hash không bắt buộc phải bằng nhau. Va chạm hash là hợp lệ.
- Khi thông tin tham gia equality không đổi, mã băm phải ổn định trong cùng lần thực thi.

Trong ví dụ `DecimalValue`, nếu chỉ ghi đè `equals` mà để `hashCode` mặc định do record sinh ra, có thể phá hợp đồng. `hashCode` mặc định dựa trên `BigDecimal.hashCode`, vốn phân biệt scale; khi đó `1.0` và `1.00` có thể bằng nhau theo `equals` tùy chỉnh nhưng có hash khác nhau.

Không dùng một hash tùy tiện chỉ để ép hai giá trị bằng nhau. Ví dụ trả về hằng số cho mọi object có thể đúng về mặt hợp đồng nhưng làm suy giảm hiệu năng nghiêm trọng trong hash collection. Tốt nhất là tạo mã băm từ chính dạng chuẩn hóa của dữ liệu tham gia equality.

## 6. Vì sao cần giữ copy invariant của record?

Ngoài hợp đồng `Object`, record còn có copy invariant: tạo record mới bằng cách truyền các giá trị lấy từ accessor của record gốc vào canonical constructor phải cho một record bằng record gốc theo `equals`.

Với `DecimalValue`:

```java
DecimalValue original =
    new DecimalValue(new BigDecimal("12.500"));

DecimalValue copy = new DecimalValue(original.value());

System.out.println(original == copy);      // false
System.out.println(original.equals(copy)); // true
System.out.println(original.hashCode() == copy.hashCode()); // true
```

Accessor `value()` trả về component `BigDecimal` đã lưu. Constructor tạo instance mới với cùng giá trị component; custom `equals` và `hashCode` vẫn nhất quán, nên copy invariant được giữ.

Không nên viết accessor biến đổi dữ liệu theo cách làm bản sao không còn bằng record gốc. Nếu muốn chuẩn hóa dữ liệu trước khi lưu, hãy làm trong canonical hoặc compact constructor. Nếu accessor trả defensive copy, hãy chắc chắn custom equality xem bản sao là cùng giá trị khi nội dung tương đương.

## 7. Tác động đến HashMap và HashSet

Khi equality đã được định nghĩa theo quy tắc nghiệp vụ, các hash collection sẽ dùng quy tắc đó:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

DecimalValue first = new DecimalValue(new BigDecimal("1.0"));
DecimalValue second = new DecimalValue(new BigDecimal("1.00"));

Set<DecimalValue> values = new HashSet<>();
values.add(first);
values.add(second);

System.out.println(values.size()); // 1

Map<DecimalValue, String> labels = new HashMap<>();
labels.put(first, "one");
labels.put(second, "one point zero");

System.out.println(labels.size()); // 1
System.out.println(labels.get(first)); // one point zero
```

Hai record bằng nhau theo custom `equals` và có cùng hash, nên `HashSet` chỉ giữ một giá trị tương đương; lần `put` thứ hai trong `HashMap` cập nhật giá trị của khóa đó.

Đây là thay đổi hành vi có chủ đích. Trước khi tùy chỉnh equality, cần xác nhận rằng hệ thống thực sự muốn gộp các giá trị có scale khác nhau. Nếu scale cần được giữ để phục vụ hiển thị, nhập liệu hoặc tính toán chính xác, có thể lưu scale ở một kiểu dữ liệu khác hoặc giữ equality mặc định.

## 8. Khi có thể chuẩn hóa constructor, hãy cân nhắc giữ implementation mặc định

Custom `equals`/`hashCode` không phải lúc nào cũng là lựa chọn đầu tiên. Nếu quy tắc nghiệp vụ có thể được thể hiện bằng một dạng chuẩn duy nhất của component, chuẩn hóa ngay khi tạo record thường đơn giản hơn:

```java
import java.math.BigDecimal;
import java.util.Objects;

record NormalizedDecimal(BigDecimal value) {
    NormalizedDecimal {
        value = Objects.requireNonNull(value, "value")
            .stripTrailingZeros();
    }
}

NormalizedDecimal first =
    new NormalizedDecimal(new BigDecimal("1.0"));
NormalizedDecimal second =
    new NormalizedDecimal(new BigDecimal("1.00"));

System.out.println(first.equals(second)); // true với equals/hashCode mặc định
```

Sau chuẩn hóa, cả hai record lưu component có dạng chuẩn tương đương. Compiler có thể sinh `equals`/`hashCode` mặc định và không cần custom logic.

Chọn giữa hai cách theo nhu cầu:

- **Chuẩn hóa constructor:** phù hợp khi dạng lưu trữ chuẩn là một phần của hợp đồng dữ liệu và không cần giữ biểu diễn đầu vào ban đầu.
- **Custom equals/hashCode:** phù hợp khi cần giữ component gốc nhưng định nghĩa equality theo một quy tắc nghiệp vụ khác, hoặc khi phép tương đương không thể được biểu diễn đơn giản bằng cách chuẩn hóa component.

Không chuẩn hóa nếu việc đó làm mất thông tin cần thiết, ví dụ scale đầu vào có ý nghĩa trong báo cáo hoặc quy trình kế toán.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ ghi đè `equals`, giữ `hashCode` mặc định | Hai record bằng nhau có thể có hash khác nhau. | Ghi đè cả hai theo cùng quy tắc. |
| `equals` dùng quy tắc A nhưng `hashCode` chuẩn hóa theo quy tắc B | Vi phạm hợp đồng hash. | Dùng cùng một dạng chuẩn hoặc phép tương đương. |
| So sánh một chiều hoặc chỉ kiểm tra một component tùy tiện | Có thể phá đối xứng hoặc bắc cầu. | Xác định đầy đủ các trường tham gia equality. |
| Bỏ qua kiểu runtime của đối tượng | Có thể so sánh nhầm các kiểu dữ liệu khác ý nghĩa. | Kiểm tra đúng record type trước khi đọc component. |
| Dùng mutable component làm cơ sở equality/hash | Hash có thể thay đổi khi record đang là khóa. | Dùng component immutable hoặc snapshot dữ liệu. |
| Trả hash hằng số cho mọi instance | Hash collection có thể suy giảm hiệu năng. | Tính hash từ dữ liệu chuẩn hóa tham gia equality. |
| Dùng `toString()` làm dữ liệu equality hoặc hash | Phụ thuộc định dạng hiển thị, không phải hợp đồng dữ liệu. | So sánh component bằng API có ngữ nghĩa rõ ràng. |
| Bỏ qua copy invariant | Bản sao tạo từ accessor có thể không bằng record gốc. | Kiểm thử việc tái tạo qua canonical constructor. |

## 10. Kiểm thử custom equality

Một bộ kiểm thử cần bao phủ các tính chất của `equals`, quan hệ với `hashCode` và copy invariant. Ví dụ kiểm tra trực tiếp:

```java
import java.math.BigDecimal;

DecimalValue a = new DecimalValue(new BigDecimal("1.0"));
DecimalValue b = new DecimalValue(new BigDecimal("1.00"));
DecimalValue c = new DecimalValue(new BigDecimal("1.000"));

// Reflexive
if (!a.equals(a)) {
    throw new AssertionError("equals must be reflexive");
}

// Symmetric
if (a.equals(b) != b.equals(a)) {
    throw new AssertionError("equals must be symmetric");
}

// Transitive
if (a.equals(b) && b.equals(c) && !a.equals(c)) {
    throw new AssertionError("equals must be transitive");
}

// Equal objects must have equal hash codes.
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("equal values must have equal hash codes");
}

// Null and unrelated types.
if (a.equals(null) || a.equals("1.0")) {
    throw new AssertionError("unexpected equality");
}

// Record copy invariant.
DecimalValue copy = new DecimalValue(a.value());
if (!a.equals(copy)) {
    throw new AssertionError("copy invariant violated");
}
```

Trong dự án thực tế, nên đưa các trường hợp này vào unit test của kiểu giá trị. Bổ sung các trường hợp biên của miền nghiệp vụ: số âm, số 0, exponent, scale âm, giá trị rất lớn và dữ liệu null nếu constructor cho phép. Không kiểm thử bằng cách khẳng định hai object khác nhau luôn có hash khác nhau vì hash collision là hợp lệ.

## 11. Phân biệt equality của Map/Set theo từng loại collection

Custom `equals`/`hashCode` của record ảnh hưởng đến collection dựa trên equality thông thường:

| Collection | Cách xác định khóa/phần tử tương đương |
| --- | --- |
| `HashMap`, `HashSet` | `hashCode()` kết hợp `equals()`. |
| `LinkedHashMap`, `LinkedHashSet` | Cùng equality semantics với collection hash tương ứng. |
| `TreeMap`, `TreeSet` | Comparator hoặc `compareTo()` trả về `0`. |
| `IdentityHashMap` | So sánh tham chiếu bằng `==`. |

`TreeMap` và `TreeSet` dùng comparator để xác định hai phần tử tương đương. Nếu comparator không nhất quán với `equals` của record, collection có thể coi hai đối tượng là cùng phần tử dù `equals` trả về `false`, hoặc ngược lại. Hãy thiết kế comparator nhất quán với equality khi cần tuân thủ đầy đủ hợp đồng `Set`/`Map`.

`IdentityHashMap` cố ý bỏ qua custom `equals` và `hashCode`, vì nó dùng identity của key. Chỉ chọn collection này khi thuật toán cần phân biệt từng instance cụ thể.

## 12. Khi nào không nên tùy biến?

Giữ implementation mặc định nếu:

- Tất cả component đều tham gia giá trị record theo đúng semantics của chúng.
- Không có quy tắc tương đương đặc biệt từ nghiệp vụ.
- Có thể chuẩn hóa đầu vào ở constructor mà không làm mất thông tin.
- Custom logic sẽ khiến người đọc khó hiểu vì sao hai record bằng nhau.

Nếu thực thể có identity nghiệp vụ riêng, vòng đời và trạng thái thay đổi, hãy cân nhắc class thông thường với ID riêng thay vì ép record mô tả entity. Record phù hợp nhất khi equality theo giá trị là điều hệ thống mong muốn.

## 13. Checklist trước khi ghi đè equals/hashCode

1. Có quy tắc nghiệp vụ cụ thể khiến equality mặc định không phù hợp không?
2. Những component nào thực sự xác định cùng một giá trị?
3. Quy tắc `equals` có phản xạ, đối xứng, bắc cầu, nhất quán và xử lý `null` đúng không?
4. Mọi cặp bằng nhau có cùng `hashCode` không?
5. Hash được tính từ cùng quy tắc hoặc dạng chuẩn hóa với `equals` chưa?
6. Dữ liệu tham gia equality/hash có immutable trong thời gian dùng làm key không?
7. Record mới tạo từ accessor của record gốc có bằng record gốc không?
8. Có thể chuẩn hóa trong constructor để dùng implementation mặc định đơn giản hơn không?
9. Collection đang dùng equality, comparator hay identity?
10. Unit test đã kiểm tra các tính chất và trường hợp biên chưa?

**Ghi nhớ:** Chỉ tùy biến `equals`/`hashCode` khi có quy tắc equality cụ thể từ nghiệp vụ. Hai phương thức phải dùng cùng semantics, tuân thủ hợp đồng `Object`, giữ copy invariant của record và tạo hash ổn định từ dữ liệu tham gia equality. Nếu chuẩn hóa constructor đã diễn tả đúng quy tắc, hãy ưu tiên giải pháp đó để giữ implementation mặc định đơn giản.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng equality và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.lang.Object`, hợp đồng `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html).
- [Java SE 26 API — `java.math.BigDecimal`, `equals`, `compareTo` và `stripTrailingZeros`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
