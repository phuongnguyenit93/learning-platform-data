# Không suy rộng quy tắc của một lớp chuẩn cho mọi lớp khác

## 1. Nguyên tắc

Trong Java, **hợp đồng chung** của `equals()`, `hashCode()`, `compareTo()` không đồng nghĩa mọi lớp chuẩn có cùng cách định nghĩa giá trị. Quan sát `String.equals()` so nội dung rồi áp dụng cho `StringBuilder`, mảng, `BigDecimal` hay kiểu thời gian sẽ dễ sai.

| Phép/API | Điều có thể khẳng định | Điều phải tra theo từng kiểu |
|---|---|---|
| `==` (tham chiếu) | Cùng object hoặc đều `null` | Literal/cache có tái dùng instance không |
| `equals()` | Phản xạ, đối xứng, bắc cầu, nhất quán, khác `null` | Các trường hoặc khía cạnh tạo equality |
| `hashCode()` | Nếu equals đúng thì hash phải bằng | Cách băm, va chạm, trường tham gia |
| `Comparable` | Kết quả âm/0/dương biểu thị trước/ngang/sau | Lớp có natural order không, `0` có tương đương equals không |
| `Comparator` | Định nghĩa thứ tự do bên gọi chọn | Nhiều giá trị khác nhau có thể so bằng `0` |
| Collection | Theo đúng hợp đồng API cụ thể | Quy tắc trùng, `null`, thứ tự, factory |

**Hash trùng không chứng minh bằng nhau**; `compareTo() == 0` cũng không mặc nhiên đồng nghĩa `equals() == true`. Dù đều là kiểu chuẩn, từng lớp có thể cố ý chọn tiêu chí khác.

## 2. `String`, `StringBuilder` và lớp tự viết

`String.equals` so chuỗi ký tự; `StringBuilder` thừa hưởng `Object.equals` nên so identity. Một lớp tự viết không ghi đè `equals` cũng vậy.

~~~java
String a = new String("Java");
String b = new String("Java");
StringBuilder x = new StringBuilder("Java");
StringBuilder y = new StringBuilder("Java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
System.out.println(x.equals(y)); // false
~~~

Đây là đoạn minh họa đặt trong `main`. Sự khác nhau đến từ **hợp đồng lớp**, không phải cả hai đều lưu văn bản. `String.equals` phân biệt case; `"Java".equalsIgnoreCase("JAVA")` trả `true` nhưng `"Java".equals("JAVA")` trả `false`. `String.CASE_INSENSITIVE_ORDER` còn có thể gom các chuỗi này trong một `TreeSet`. Không dùng `==` để so nội dung dựa trên quan sát về string interning.

## 3. `BigDecimal` và wrapper số

~~~java
BigDecimal n1 = new BigDecimal("2.0");
BigDecimal n2 = new BigDecimal("2.00");
System.out.println(n1.equals(n2));       // false
System.out.println(n1.compareTo(n2) == 0); // true
~~~

Cần `java.math.BigDecimal`. `BigDecimal.equals` xét **scale** (1 so với 2), còn `compareTo` xét giá trị số. Vì vậy `HashSet<BigDecimal>` có thể giữ cả hai, trong khi `TreeSet<BigDecimal>` với natural order chỉ giữ một. `String.compareTo == 0` nhất quán với `String.equals` nhưng **không nên suy quy tắc đó sang BigDecimal**.

Tương tự, `Integer.valueOf(10).equals(Long.valueOf(10L))` trả `false`, dù cùng số 10, vì `Integer.equals` yêu cầu đúng kiểu wrapper. Với `Double`, `Double.NaN == Double.NaN` là `false` ở primitive, nhưng hai `Double` chứa `NaN` bằng nhau qua `Double.equals`. `Double.equals(-0.0, +0.0)` không phải cú pháp API; gọi qua hai wrapper thì trả `false`, trong khi `-0.0 == +0.0` trên primitive là `true`.

Không suy từ so sánh số học sang `equals` của object. Khi thiết kế dữ liệu tiền tệ, hãy quyết định có tính scale hay chỉ lượng số, rồi dùng một tiêu chí nhất quán trong key và collection.

## 4. Mảng, record và collection

Mảng Java mặc định không ghi đè `Object.equals`: hai `int[]` khác instance có cùng phần tử vẫn không bằng nhau qua `array.equals`. Dùng `Arrays.equals` để so từng phần tử của mảng một chiều, và `Arrays.deepEquals` khi cần so sâu mảng `Object[]` có phần tử lồng.

`record` tự sinh `equals`/`hashCode` dựa trên component, nhưng **component là array vẫn so identity**; record không biến array thành deep equality.

Các collection khác nhau:

- `List.equals` xét từng phần tử **theo thứ tự**; một `ArrayList` có thể bằng `List.of` cùng chuỗi phần tử.
- `Set.equals` xét **cùng phần tử**, không phụ thuộc thứ tự duyệt; `HashSet` có thể bằng `LinkedHashSet` cùng tập phần tử.
- `HashSet` dùng `equals/hashCode` để nhận biết phần tử trùng; `TreeSet` dùng `compareTo` hoặc comparator trả `0` để nhận biết khóa trùng.
- `HashSet.add` phần tử trùng trả `false`, nhưng factory `Set.of` với phần tử trùng **ném `IllegalArgumentException`**. `List.of` cho phép phần tử trùng. `HashSet` chứa được một `null`; factory `Set.of` từ chối `null`.

Ví dụ comparator chỉ theo độ dài khiến `"hi"` và `"ok"` ngang hàng trong `TreeSet`, dù `String.equals` giữa chúng trả `false`. Muốn giữ cả hai, dùng comparator có tiêu chí phụ hoặc collection khác.

## 5. Date-time: cùng thời điểm khác equality

`OffsetDateTime.parse("2026-01-01T10:00:00+07:00")` và `OffsetDateTime.parse("2026-01-01T03:00:00Z")` đại diện cùng instant trên dòng thời gian.

`isEqual()` giữa chúng là `true`; `equals()` là `false`, vì `equals` xét giá trị biểu diễn gồm offset. Nếu nghiệp vụ hỏi **cùng instant**, dùng `isEqual` hoặc so `Instant`. Nếu hỏi **cùng giá trị OffsetDateTime**, dùng `equals`. Không dùng hợp đồng của `LocalDate` hay `Instant` để tự suy hành vi của `OffsetDateTime`/`ZonedDateTime`.

## 6. Chương trình Java 17 chạy được

Lưu thành file **`StandardContractsDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class StandardContractsDemo {
    record Box(int[] values) {}

    public static void main(String[] args) {
        String s1 = new String("Java");
        String s2 = new String("Java");
        System.out.println("String identity: " + (s1 == s2));
        System.out.println("String equals: " + s1.equals(s2));
        System.out.println("Builder equals: "
                + new StringBuilder("Java")
                .equals(new StringBuilder("Java")));

        System.out.println("Integer vs Long: "
                + Integer.valueOf(10).equals(Long.valueOf(10L)));
        System.out.println("Primitive NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("Wrapper NaN: "
                + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("Decimal equals: " + a.equals(b));
        System.out.println("Decimal compare zero: "
                + (a.compareTo(b) == 0));
        System.out.println("HashSet decimals: "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("TreeSet decimals: "
                + new TreeSet<>(List.of(a, b)).size());

        int[] x = {1, 2};
        int[] y = {1, 2};
        System.out.println("Array equals: " + x.equals(y));
        System.out.println("Arrays.equals: " + Arrays.equals(x, y));
        System.out.println("Record array equals: "
                + new Box(x).equals(new Box(y)));

        List<String> listA = List.of("a", "b");
        List<String> listB = new ArrayList<>(List.of("a", "b"));
        Set<String> setA = new HashSet<>(List.of("a", "b"));
        Set<String> setB = new LinkedHashSet<>(List.of("b", "a"));
        System.out.println("List across classes: "
                + listA.equals(listB));
        System.out.println("Set across classes: "
                + setA.equals(setB));

        TreeSet<String> byLength = new TreeSet<>(
                Comparator.comparingInt(String::length));
        byLength.add("hi");
        byLength.add("ok");
        System.out.println("TreeSet length only: " + byLength.size());

        System.out.println("String hash collision: "
                + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("Collision equals: "
                + "Aa".equals("BB"));

        OffsetDateTime hcm = OffsetDateTime.parse(
                "2026-01-01T10:00:00+07:00");
        OffsetDateTime utc = OffsetDateTime.parse(
                "2026-01-01T03:00:00Z");
        System.out.println("Date same instant: " + hcm.isEqual(utc));
        System.out.println("Date equals: " + hcm.equals(utc));

        try {
            Set.of("x", "x");
        } catch (IllegalArgumentException expected) {
            System.out.println("Set.of duplicate: rejected");
        }
    }
}
~~~

Chạy với JDK 17:

~~~bash
javac StandardContractsDemo.java
java StandardContractsDemo
~~~

Đầu ra:

~~~text
String identity: false
String equals: true
Builder equals: false
Integer vs Long: false
Primitive NaN: false
Wrapper NaN: true
Decimal equals: false
Decimal compare zero: true
HashSet decimals: 2
TreeSet decimals: 1
Array equals: false
Arrays.equals: true
Record array equals: false
List across classes: true
Set across classes: true
TreeSet length only: 1
String hash collision: true
Collision equals: false
Date same instant: true
Date equals: false
Set.of duplicate: rejected
~~~

Đầu ra chỉ dùng boolean/kích thước; không dựa vào thứ tự duyệt không được bảo đảm của `HashSet`. `"Aa"` và `"BB"` là một va chạm hash có thật nhưng hai chuỗi không bằng nhau; collision **không** làm hai phần tử logic trở thành một.

## 7. Cách áp dụng và kiểm chứng

Khi gặp lớp chuẩn mới, hãy **đọc Javadoc của đúng lớp** thay vì sao chép quy tắc từ lớp quen thuộc:

1. Xác định `equals` đang dùng identity, giá trị, kiểu runtime, ID hay trường nào; kiểm tra `null`.
2. Kiểm tra `hashCode` cùng dữ liệu quyết định equality. Nếu object đã làm khóa hash collection, tránh thay đổi trường tham gia equality/hash.
3. Kiểm tra lớp có `Comparable` không và `compareTo == 0` có nhất quán với `equals` không. Nếu truyền comparator, xét tiêu chí phá hòa.
4. Kiểm tra collection/factory: `HashSet`, `TreeSet`, `List.of`, `Set.of` có hợp đồng khác nhau về trùng, `null`, thứ tự.
5. Thử cặp khác instance cùng dữ liệu; hai kiểu số; `BigDecimal` khác scale; array lồng; `NaN`; cùng instant khác offset; hash trùng nhưng giá trị khác.
6. Chọn quan hệ đúng với **yêu cầu nghiệp vụ**: so số bất kể scale có thể cần `compareTo`; so instant cần `isEqual`/`Instant`; so nội dung mảng cần `Arrays.equals`.

## 8. Lỗi thường gặp

| Giả định sai | Hệ quả | Cách sửa |
|---|---|---|
| Có cùng trường thì object tự bằng nhau | Lớp không override `equals` vẫn dùng identity | Xem hợp đồng lớp, tự định nghĩa value object nếu cần |
| Mọi kiểu văn bản giống `String` | `StringBuilder.equals` vẫn dùng identity | Dùng phép so nội dung thích hợp |
| Số giống nhau thì wrapper luôn equals | `Integer` khác `Long`, BigDecimal xét scale | Chọn kiểu và chính sách so sánh |
| `compareTo == 0` đồng nghĩa `equals` | Sai với BigDecimal/comparator tùy chỉnh | Kiểm tra nghĩa comparator |
| Hash bằng nhau là object bằng nhau | Collision bị hiểu thành trùng | So equality, không kết luận từ hash |
| Record tự so sâu array | Hai array nội dung giống nhau vẫn khác identity | Thiết kế lại component hoặc override đúng |
| Tất cả set khử trùng giống nhau | Comparator hoặc factory làm kết quả khác | Đọc API cụ thể |
| Cùng instant thì date-time `equals` | Khác offset có thể `equals false` | So instant khi đó là mục tiêu |

## 9. Câu hỏi tự kiểm tra

**1.** Hai `StringBuilder("A")` cùng nội dung nhưng `equals false`: có mâu thuẫn với `String.equals` không?  
**Đáp án:** Không. Hai lớp có hợp đồng khác nhau.

**2.** Vì sao `HashSet<BigDecimal>` giữ `2.0` và `2.00`, còn `TreeSet<BigDecimal>` chỉ giữ một?  
**Đáp án:** `equals` xét scale; `compareTo` xét lượng số.

**3.** Hai mảng cùng phần tử nhưng `array.equals` sai; nên dùng gì?  
**Đáp án:** `Arrays.equals` hoặc `Arrays.deepEquals` phù hợp với cấu trúc.

**4.** `TreeSet` comparator chỉ xét độ dài có giữ cả `"hi"` và `"ok"` không?  
**Đáp án:** Không; comparator trả `0`.

**5.** `OffsetDateTime.isEqual` đúng nhưng `equals` sai có hợp lệ không?  
**Đáp án:** Có; cùng instant khác biểu diễn offset.

**Ghi nhớ:** Bất biến chung của `Object` là nền tảng, còn **nghĩa cụ thể của equality, hash, ordering và collection behavior phải được kiểm tra ở mỗi lớp/API**.
