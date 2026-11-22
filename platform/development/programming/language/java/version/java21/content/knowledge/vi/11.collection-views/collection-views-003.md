# Reversed hai lần và cách kiểm tra thứ tự theo hợp đồng

Trong Java 21, các collection có encounter order cung cấp phương thức `reversed()` để nhìn cùng dữ liệu theo thứ tự ngược lại. Kết quả là một view được liên kết với collection gốc. Theo hợp đồng của API Sequenced Collections, gọi `reversed()` trên view đó sẽ trả lại chính collection ban đầu.

Khi kiểm thử, cần phân biệt ba điều: thứ tự mà implementation cam kết, view đảo ngược và snapshot dùng để so sánh. Đặc biệt, `Set.equals()` và `Map.equals()` không so sánh encounter order, nên không thể dùng trực tiếp chúng để chứng minh một sequenced set hoặc sequenced map có thứ tự mong muốn.

## 1. reversed() đảo encounter order hiện có

`reversed()` không sắp xếp phần tử theo giá trị. Nó đảo ngược encounter order mà collection đang cung cấp. Ví dụ, nếu một list có thứ tự `An`, `Binh`, `Chi`, view đảo ngược sẽ duyệt `Chi`, `Binh`, `An`.

```java
import java.util.ArrayList;
import java.util.List;

static void showReverse() {
    List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));
    List<String> reverse = names.reversed();

    System.out.println(names);   // [An, Binh, Chi]
    System.out.println(reverse); // [Chi, Binh, An]
}
```

View giữ cùng các phần tử. Không có thao tác sao chép toàn bộ phần tử chỉ vì gọi `reversed()`; collection được quan sát theo chiều encounter order ngược lại.

## 2. reversed().reversed() trả lại collection gốc

Hợp đồng `SequencedCollection.reversed()` quy định view trả về có phương thức `reversed()` trả lại collection ban đầu. Vì vậy, đảo hai lần khôi phục đúng collection gốc, không tạo một bản sao thứ hai.

```java
import java.util.ArrayList;
import java.util.List;

static void reverseTwice() {
    List<String> original = new ArrayList<>(List.of("A", "B", "C"));

    List<String> once = original.reversed();
    List<String> twice = once.reversed();

    System.out.println(once);   // [C, B, A]
    System.out.println(twice);  // [A, B, C]
    System.out.println(twice == original); // true
}
```

Phép so sánh `==` trong ví dụ xác nhận danh tính object: view đảo ngược lần thứ hai trả lại chính reference của collection gốc theo hợp đồng API. Đây là kiểm tra phù hợp cho bảo đảm cụ thể này; nó khác với kiểm tra hai collection có cùng phần tử hay không bằng `equals()`.

## 3. Reverse view được liên kết với collection gốc

View trả về từ `reversed()` được backing bởi collection gốc. Thay đổi qua một phía sẽ được phản ánh khi quan sát phía còn lại, miễn là implementation hỗ trợ thao tác thay đổi tương ứng.

```java
import java.util.ArrayList;
import java.util.List;

static void modifyThroughReverseView() {
    List<String> original = new ArrayList<>(List.of("first", "middle", "last"));
    List<String> reverse = original.reversed();

    reverse.set(0, "new-last");
    System.out.println(original);
    // [first, middle, new-last]

    original.add("newest");
    System.out.println(reverse);
    // [newest, new-last, middle, first]
}
```

`set(0, ...)` trên view đảo ngược thay đổi phần tử cuối của list gốc. Khi thêm phần tử vào cuối list gốc, phần tử đó xuất hiện ở đầu view đảo ngược.

Không nên coi reverse view là snapshot bất biến. Nếu cần một bản chụp độc lập về encounter order tại một thời điểm, hãy tạo snapshot riêng.

## 4. Tạo snapshot để kiểm tra thứ tự

Với `List`, `List.copyOf()` tạo một list không thể sửa đổi chứa các phần tử theo encounter order lúc tạo snapshot. Có thể dùng snapshot để so sánh với thứ tự kỳ vọng:

```java
import java.util.ArrayList;
import java.util.List;

static void verifyListOrder() {
    List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

    List<String> expected = List.of("Chi", "Binh", "An");
    List<String> actual = List.copyOf(names.reversed());

    if (!expected.equals(actual)) {
        throw new AssertionError("Unexpected encounter order: " + actual);
    }
}
```

Snapshot là bản sao nông và không thay đổi khi collection gốc được cập nhật sau đó. Nếu phần tử bên trong là object mutable, snapshot vẫn chứa cùng các reference đến object đó; nó chỉ cố định cấu trúc và thứ tự của list snapshot.

`List.copyOf()` không chấp nhận phần tử `null`. Nếu collection nguồn cho phép `null` và dữ liệu có thể chứa giá trị này, hãy dùng một bản sao phù hợp như `new ArrayList<>(source.reversed())` thay vì `List.copyOf()`.

## 5. Vì sao Set.equals() không kiểm tra thứ tự?

`SequencedSet` vừa là `Set` vừa là `SequencedCollection`. Tuy có encounter order, nó vẫn giữ hợp đồng equality của `Set`: hai set bằng nhau nếu chứa cùng các phần tử, bất kể thứ tự. Vì vậy, một set và view đảo ngược của nó thường bằng nhau theo `equals()`.

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

static void verifySetOrder() {
    SequencedSet<String> names =
            new LinkedHashSet<>(List.of("An", "Binh", "Chi"));
    SequencedSet<String> reverse = names.reversed();

    System.out.println(names.equals(reverse)); // true

    List<String> expected = List.of("Chi", "Binh", "An");
    List<String> actual = List.copyOf(reverse);
    System.out.println(expected.equals(actual)); // true
}
```

`names.equals(reverse)` chỉ xác nhận hai set có cùng phần tử. `List.copyOf(reverse)` chuyển encounter order thành một list; equality của list có xét vị trí, nên phép so sánh này mới kiểm tra đúng thứ tự cần xác nhận.

`hashCode()` của `Set` cũng được định nghĩa không phụ thuộc encounter order. Không dùng hash code để kiểm tra một sequenced set đang duyệt theo chiều nào.

## 6. Kiểm tra thứ tự theo đúng hợp đồng implementation

Không phải mọi collection đều cam kết cùng một kiểu thứ tự. Trước khi viết assertion, hãy xác định hợp đồng của implementation đang dùng:

| Collection | Hợp đồng encounter order | Điều có thể kiểm tra |
|---|---|---|
| `ArrayList` | Thứ tự phần tử trong list | So sánh trực tiếp với list kỳ vọng hoặc snapshot list |
| `LinkedHashSet` | Thứ tự liên kết được duy trì theo chính sách của set | Chuyển sang `List` để kiểm tra thứ tự duyệt; kiểm tra riêng thao tác reposition ở hai đầu |
| `TreeSet` | Thứ tự theo comparator hoặc natural ordering | Kiểm tra thứ tự theo comparator; reverse view đi theo chiều encounter order ngược |
| `HashSet` | Không cam kết encounter order cụ thể | Chỉ kiểm tra tính thành viên/equality của set, không khẳng định thứ tự duyệt |

`reversed()` chỉ đảo thứ tự mà collection cung cấp. Nếu collection gốc không cam kết encounter order cụ thể, ứng dụng không thể dựa vào một chuỗi kết quả cụ thể sau khi đảo.

Ví dụ, không nên viết kiểm thử yêu cầu `HashSet` luôn trả về `[A, B, C]` hoặc reverse của nó luôn là `[C, B, A]`. Những kỳ vọng đó không thuộc hợp đồng của `HashSet`.

## 7. Kiểm tra SequencedMap theo thứ tự entry

`SequencedMap` cũng cung cấp `reversed()` và view của các entry theo encounter order. Tuy nhiên, `Map.equals()` so sánh ánh xạ key-value, không xét thứ tự entry. Khi cần kiểm tra thứ tự, hãy lấy sequenced entry set rồi tạo list snapshot.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SequencedMap;

static void verifyMapOrder() {
    SequencedMap<String, Integer> scores = new LinkedHashMap<>();
    scores.putLast("An", 10);
    scores.putLast("Binh", 9);
    scores.putLast("Chi", 8);

    var reverseEntries = scores.reversed().sequencedEntrySet();
    var actual = List.copyOf(reverseEntries);
    var expected = List.of(
            Map.entry("Chi", 8),
            Map.entry("Binh", 9),
            Map.entry("An", 10));

    if (!expected.equals(actual)) {
        throw new AssertionError(actual);
    }
}
```

Ví dụ trên cần import thêm `java.util.Map`. `sequencedEntrySet()` cung cấp entry set có encounter order; `List.copyOf()` cố định thứ tự tại thời điểm tạo snapshot. Không dùng `scores.equals(scores.reversed())` để xác nhận thứ tự vì equality của map không xét thứ tự.

## 8. View đảo ngược và tính bất biến

`reversed()` không tự biến collection thành immutable. Khả năng thay đổi của view theo hợp đồng và implementation nền:

- Nếu collection gốc hỗ trợ cập nhật, reverse view hỗ trợ những thao tác cập nhật tương ứng được collection đó cho phép.
- Nếu collection gốc không thể sửa đổi, thao tác thay đổi qua reverse view cũng không được hỗ trợ và có thể ném `UnsupportedOperationException`.
- Nếu cần view chỉ đọc, dùng wrapper unmodifiable phù hợp hoặc collection bất biến; nếu cần snapshot tách biệt, tạo bản sao riêng.

Java 21 cung cấp các wrapper sequenced không thể sửa đổi trong `Collections`, chẳng hạn `unmodifiableSequencedCollection`, `unmodifiableSequencedSet` và `unmodifiableSequencedMap`. Wrapper ngăn sửa đổi qua chính nó, nhưng nếu backing collection bên dưới vẫn bị thay đổi qua một reference khác, wrapper vẫn phản ánh dữ liệu mới đó. Đây là view chỉ đọc, không phải snapshot độc lập.

Ví dụ tạo snapshot bất biến theo encounter order:

```java
import java.util.List;

static List<String> immutableSnapshot(List<String> source) {
    return List.copyOf(source.reversed());
}
```

Kết quả là một list snapshot không thể sửa đổi, có thứ tự đảo ngược so với source tại thời điểm gọi. Những thay đổi về sau của source không làm thay đổi cấu trúc list snapshot.

## 9. Bộ kiểm tra thực tế cho reverse view

Khi kiểm thử một collection view, nên kiểm tra các thuộc tính độc lập thay vì chỉ dựa vào `toString()`:

1. **Thứ tự view:** tạo list snapshot và so sánh với list kỳ vọng.
2. **Đảo hai lần:** kiểm tra `original.reversed().reversed() == original` theo hợp đồng của API.
3. **Liên kết dữ liệu:** với collection mutable, thay đổi qua view rồi xác nhận dữ liệu gốc phản ánh thay đổi đó.
4. **Equality:** không dùng `Set.equals()` hoặc `Map.equals()` để xác nhận thứ tự.
5. **Implementation:** chỉ assert thứ tự cụ thể khi implementation cam kết encounter order đó.
6. **Tính bất biến:** kiểm tra thao tác cập nhật trên wrapper hoặc collection immutable không được hỗ trợ khi đây là hợp đồng cần bảo vệ.

Ví dụ assertion ngắn cho list:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

static void assertReverseContract(List<String> original) {
    List<String> reverse = original.reversed();
    List<String> expected = new ArrayList<>(original);

    Collections.reverse(expected);
    List<String> actual = new ArrayList<>(reverse);
    if (!expected.equals(actual)) {
        throw new AssertionError("Unexpected reverse order: " + actual);
    }
    if (reverse.reversed() != original) {
        throw new AssertionError("Double reverse must return original");
    }
}
```

Trong kiểm thử thực tế, nên tạo list kỳ vọng đảo ngược trực tiếp từ fixture để assertion dễ đọc. Nếu dùng một thao tác đảo tại chỗ để dựng expected, hãy đảo một bản sao mutable; không thay đổi fixture đang được kiểm thử.

## 10. Biên dịch với Java 21

`SequencedCollection`, `SequencedSet`, `SequencedMap` và các phương thức `reversed()` được đưa vào Java 21 qua JEP 431. Đây là API đã final, không cần bật Preview.

```bash
javac --release 21 -d out src/ReversedViewDemo.java
java -cp out ReversedViewDemo
```

Đặt compiler release hoặc toolchain về Java 21 để compiler xác nhận API đang sử dụng có trong phiên bản mục tiêu. Không thêm `--enable-preview` cho các ví dụ trong bài.

## 11. Tài liệu tham khảo

- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [Java SE 21 API — SequencedCollection.reversed()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html#reversed())
- [Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Java SE 21 API — Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html)
- [Java SE 21 API — Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html)
