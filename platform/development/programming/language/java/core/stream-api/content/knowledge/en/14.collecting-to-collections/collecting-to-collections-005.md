# Giữ thứ tự gặp bằng `ArrayList` và `LinkedHashSet`

## 1. Mục tiêu bài học

Trong **Java Stream API**, một pipeline khai báo thường lấy dữ liệu từ nguồn, thực hiện các thao tác trung gian lazy như `filter`, `map` và kết thúc bằng `collect`. Khi thu kết quả thành một collection, kiểu collection quyết định **có giữ giá trị trùng hay không**, **duyệt lại theo thứ tự nào** và **có thể tiếp tục thêm/xóa phần tử không**.

Bài này thuộc chương **Thu thập thành Collection** của module **`JAVA_STREAM_API`**, tập trung vào hai trường hợp thực tế:

- **`ArrayList`:** giữ tất cả phần tử, kể cả các phần tử trùng nhau, theo **thứ tự gặp** (*encounter order*) của stream có thứ tự.
- **`LinkedHashSet`:** chỉ giữ một phần tử cho mỗi nhóm bằng nhau theo `equals`/`hashCode`, đồng thời giữ **thứ tự xuất hiện đầu tiên** của các giá trị duy nhất.

Sau bài học, bạn có thể:

1. Phân biệt thứ tự gặp của nguồn stream với thứ tự duyệt collection kết quả.
2. Dùng `Collectors.toCollection(ArrayList::new)` và `Collectors.toCollection(LinkedHashSet::new)` để chọn rõ loại collection cần nhận.
3. Dự đoán kết quả của pipeline có `filter`, `map`, `distinct` và `sorted`.
4. Nhận biết ranh giới bảo đảm thứ tự ở nguồn có thứ tự, nguồn không có thứ tự và pipeline song song.
5. Tránh nhầm lẫn giữa `toList`, `toSet`, `toCollection` và những vấn đề liên quan đến đối tượng thay đổi được.

Những nguyên tắc này cũng hữu ích khi tiếp tục học grouping, collector tùy chỉnh, Spliterator và hiệu năng xử lý song song.

## 2. Thứ tự gặp (*encounter order*) là gì?

**Thứ tự gặp** là thứ tự phần tử do nguồn stream xác định, nếu nguồn có thứ tự. Ví dụ, một `List` có thứ tự theo vị trí các phần tử:

```java
import java.util.Arrays;
import java.util.List;

List<String> khoaHoc = Arrays.asList(
    "Java Core", "Go", "Java Stream", "Go", "Kotlin"
);
```

Stream tạo bằng `khoaHoc.stream()` có thứ tự gặp:

```text
Java Core → Go → Java Stream → Go → Kotlin
```

Không phải nguồn nào cũng có thứ tự gặp được bảo đảm:

| Nguồn | Có thứ tự gặp được bảo đảm? | Ghi chú |
| --- | --- | --- |
| `ArrayList.stream()` | Có | Theo thứ tự các phần tử trong list. |
| `LinkedList.stream()` | Có | Theo thứ tự duyệt list. |
| `Arrays.stream(array)` | Có | Theo thứ tự chỉ số mảng. |
| `IntStream.range(0, 5)` | Có | Theo thứ tự tăng từ 0 đến 4. |
| `LinkedHashSet.stream()` | Có | Theo thứ tự chèn của set. |
| `HashSet.stream()` | Không | Thứ tự duyệt không được bảo đảm. |
| `HashMap.keySet().stream()` | Không | Không nên dựa vào thứ tự khóa của `HashMap`. |

**Điểm quan trọng:** một nguồn `HashSet` có thể tình cờ được in cùng thứ tự trong vài lần chạy, nhưng điều đó không tạo ra một hợp đồng bảo đảm thứ tự. Chuyển kết quả vào `LinkedHashSet` không thể tự suy ra thứ tự ban đầu mà nguồn chưa từng cam kết.

Các thao tác trung gian có thể giữ, thay đổi hoặc loại bỏ ràng buộc thứ tự:

- `filter` giữ thứ tự tương đối của các phần tử còn lại trong một ordered stream.
- `map` biến đổi giá trị nhưng giữ thứ tự vị trí đầu ra đối với ordered stream.
- `sorted` tạo thứ tự sắp xếp mới.
- `unordered` cho phép pipeline **bỏ ràng buộc** về thứ tự gặp.
- `distinct` trên ordered stream giữ phần tử đầu tiên của mỗi giá trị bằng nhau.

Vì vậy, muốn đánh giá thứ tự kết quả, hãy hỏi: **nguồn có thứ tự không và các bước trước `collect` đã làm gì với thứ tự đó?**

## 3. Collector tường minh: `toCollection`

Java 8 cung cấp phương thức:

```java
static <T, C extends Collection<T>> Collector<T, ?, C>
    toCollection(Supplier<C> collectionFactory)
```

`Collectors.toCollection` nhận một **supplier** dùng để tạo collection kết quả. Với hai kiểu đang học:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;

// Thu thành ArrayList:
.collect(Collectors.toCollection(ArrayList::new));

// Thu thành LinkedHashSet:
.collect(Collectors.toCollection(LinkedHashSet::new));
```

Cú pháp `ArrayList::new` và `LinkedHashSet::new` là **constructor reference**: supplier tạo collection mới khi collector cần tích lũy dữ liệu. Bạn có thể viết tương đương bằng lambda `() -> new ArrayList<>()` hoặc `() -> new LinkedHashSet<>()`.

`toCollection` cho phép quyết định **kiểu collection cụ thể**. Trên một ordered stream, collector nhận phần tử theo thứ tự gặp và tích lũy chúng; `ArrayList` giữ thứ tự đó khi duyệt, còn `LinkedHashSet` giữ thứ tự chèn của những phần tử đầu tiên chưa trùng.

### Ví dụ hoàn chỉnh: thu cả danh sách và danh sách không trùng

Chương trình sau chạy trên **Java 8 trở lên**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

public class ThuThapTheoThuTu {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList(
            "Java", "Go", "Java", "Kotlin", "Go", "Python"
        );

        ArrayList<String> tatCa = ten.stream()
            .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<String> duyNhat = ten.stream()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(tatCa);
        System.out.println(duyNhat);
        System.out.println(tatCa.getClass().getSimpleName());
        System.out.println(duyNhat.getClass().getSimpleName());
    }
}
```

Kết quả:

```text
[Java, Go, Java, Kotlin, Go, Python]
[Java, Go, Kotlin, Python]
ArrayList
LinkedHashSet
```

Ta tạo **hai stream riêng** bằng `ten.stream()` bởi một stream không thể được dùng lại sau khi chạy terminal operation `collect`.

So sánh:

| Yêu cầu | `ArrayList` | `LinkedHashSet` |
| --- | --- | --- |
| Giữ hai lần xuất hiện của `"Java"` | Có | Không |
| Giữ thứ tự xuất hiện từ nguồn ordered | Có | Có, đối với các giá trị duy nhất |
| Truy cập phần tử bằng chỉ số `get(0)` | Có | Không |
| Tìm kiếm phần tử bằng `contains` | Có, duyệt tuyến tính | Thường hiệu quả hơn nhờ bảng băm |
| Cho phép thêm/xóa phần tử | Có | Có |
| Chứa phần tử `null` | Có, có thể lặp lại | Có, tối đa một `null` |

Không nên chọn `LinkedHashSet` chỉ vì muốn giữ thứ tự nếu nghiệp vụ vẫn cần giữ đầy đủ các bản ghi trùng. Đó là hai yêu cầu khác nhau.

## 4. Dùng `ArrayList` khi phải giữ mọi phần tử

### 4.1. `filter` và `map` không tự loại trùng

`ArrayList` đặc biệt hữu ích khi cần giữ bản ghi theo thứ tự thời gian, danh sách kết quả tìm kiếm hoặc lịch sử sự kiện mà **hai bản ghi bằng nhau vẫn có ý nghĩa**.

```java
List<String> suKien = Arrays.asList(
    "login", "error", "login", "logout", "login"
);

ArrayList<String> lichSu = suKien.stream()
    .filter(s -> !s.equals("error"))
    .map(String::toUpperCase)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(lichSu);
// [LOGIN, LOGIN, LOGOUT, LOGIN]
```

Trong ví dụ này, cả ba lần `"login"` vẫn tồn tại; `filter` chỉ loại `"error"`. `map` biến đổi từng giá trị chứ không xóa phần tử trùng.

### 4.2. Thêm `sorted` khi cần thứ tự cụ thể

`ArrayList` giữ thứ tự **đầu vào của bước thu thập**. Nếu pipeline đã sắp xếp, list phản ánh thứ tự sau sắp xếp:

```java
List<String> ten = Arrays.asList("Kotlin", "Java", "Go");

ArrayList<String> theoAlphabet = ten.stream()
    .sorted()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(theoAlphabet); // [Go, Java, Kotlin]
```

Ở đây `ArrayList` không tự sắp xếp; chính `sorted()` làm thay đổi thứ tự gặp trước khi thu.

### 4.3. Vì sao không luôn dùng `Collectors.toList()`?

Cách viết sau cũng có thể thu các phần tử vào một list:

```java
List<String> ketQua = ten.stream()
    .collect(Collectors.toList());
```

Tuy nhiên, **`Collectors.toList()` không cam kết kiểu triển khai, khả năng sửa đổi, tính thread-safe hay serializability** của list kết quả. Trên một số JDK nó là `ArrayList`, nhưng không nên xem đó là hợp đồng API.

Nếu **thực sự cần `ArrayList`**, hãy viết:

```java
ArrayList<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(ArrayList::new));

ketQua.add("Python");
System.out.println(ketQua); // [Kotlin, Java, Go, Python]
```

Từ **Java 16**, `stream.toList()` thu về list **không cho phép sửa** và vẫn giữ thứ tự gặp nếu stream có thứ tự. Nếu yêu cầu là list có thể thay đổi với kiểu cụ thể, `toCollection(ArrayList::new)` vẫn là lựa chọn rõ ràng.

## 5. Dùng `LinkedHashSet` khi cần duy nhất và giữ vị trí đầu tiên

`LinkedHashSet` kết hợp hai đặc điểm:

1. Không chứa hai phần tử được coi là bằng nhau theo hợp đồng `equals` và `hashCode`.
2. Duyệt phần tử theo **thứ tự chèn**.

Với stream có thứ tự, giá trị duy nhất nào xuất hiện trước sẽ được chèn trước:

```java
List<String> ten = Arrays.asList(
    "Go", "Java", "Go", "Kotlin", "Java", "Python"
);

LinkedHashSet<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(ketQua);
// [Go, Java, Kotlin, Python]
```

Khi `"Go"` hoặc `"Java"` xuất hiện lại, lần chèn trùng **không đổi vị trí** của phần tử đã được chèn trước.

### 5.1. Thêm lại phần tử trùng không đưa nó về cuối

```java
LinkedHashSet<String> set = new LinkedHashSet<>();
set.add("A");
set.add("B");
set.add("A");

System.out.println(set); // [A, B]
```

Để chuyển `"A"` về cuối theo quy tắc chèn, phải xóa rồi thêm:

```java
set.remove("A");
set.add("A");
System.out.println(set); // [B, A]
```

Không nên dùng thao tác xóa/thêm khi mục tiêu chỉ là khử trùng; nếu thứ tự đầu tiên quan trọng, chỉ cần thu trực tiếp.

### 5.2. `LinkedHashSet` có khác `HashSet` không?

Cả hai đều loại giá trị trùng, nhưng `HashSet` không bảo đảm thứ tự duyệt:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;

HashSet<String> khongCamKetThuTu = ten.stream()
    .collect(Collectors.toCollection(HashSet::new));

LinkedHashSet<String> giuThuTu = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

Nếu người dùng cần danh sách nhãn duy nhất theo **thứ tự xuất hiện lần đầu trong dữ liệu đầu vào**, sử dụng `LinkedHashSet` giúp diễn đạt chính xác yêu cầu. Nếu không quan tâm thứ tự, `HashSet` có thể là lựa chọn phù hợp.

`LinkedHashSet` **không sắp xếp theo bảng chữ cái**. Để tạo thứ tự chữ cái, cần `sorted()` trước khi collect hoặc một collection có ngữ nghĩa sắp xếp như `TreeSet` (ngữ nghĩa khác với thứ tự gặp).

## 6. Quy tắc trùng lặp: `equals` và `hashCode`

`LinkedHashSet` xác định trùng lặp theo ngữ nghĩa của `Set`. Với `String`, hai chuỗi bằng nhau theo `equals` được coi là trùng, trong khi `"Java"` và `"java"` khác nhau:

```java
List<String> ten = Arrays.asList(
    "Java", "java", "JAVA", "Go"
);

LinkedHashSet<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(ketQua);
// [Java, java, JAVA, Go]
```

Nếu nghiệp vụ muốn so sánh không phân biệt hoa/thường, phải chuẩn hóa giá trị **trước khi thu**:

```java
import java.util.Locale;

LinkedHashSet<String> chuanHoa = ten.stream()
    .map(s -> s.toLowerCase(Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(chuanHoa); // [java, go]
```

Đây là thao tác thay đổi dữ liệu: mọi giá trị đều được đưa về chữ thường. Nếu cần **giữ nguyên cách viết lần đầu** nhưng kiểm tra trùng không phân biệt hoa/thường, cần thiết kế khóa so sánh riêng, ví dụ dùng `LinkedHashMap` với khóa chuẩn hóa. `LinkedHashSet<String>` tự nó không nhận `Comparator` tùy chỉnh.

### 6.1. Đối tượng tùy chỉnh phải tuân thủ hợp đồng bằng nhau

Hai đối tượng có cùng mã nghiệp vụ có thể được coi là một phần tử, dù các thuộc tính hiển thị khác nhau. Ví dụ Java 8:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class LoaiBanGhiTrung {
    static final class GiaoDich {
        final String ma;
        final String moTa;

        GiaoDich(String ma, String moTa) {
            this.ma = ma;
            this.moTa = moTa;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof GiaoDich)) return false;
            GiaoDich other = (GiaoDich) obj;
            return Objects.equals(ma, other.ma);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(ma);
        }

        @Override
        public String toString() {
            return ma + ":" + moTa;
        }
    }

    public static void main(String[] args) {
        List<GiaoDich> nguon = Arrays.asList(
            new GiaoDich("A01", "Bản đầu"),
            new GiaoDich("B02", "Bản khác"),
            new GiaoDich("A01", "Bản cập nhật")
        );

        LinkedHashSet<GiaoDich> duyNhat = nguon.stream()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(duyNhat);
        // [A01:Bản đầu, B02:Bản khác]
    }
}
```

Nhờ `equals` và `hashCode` cùng dựa trên `ma`, bản ghi `"A01"` thứ hai bị xem là trùng. `LinkedHashSet` giữ **đối tượng `"A01"` được gặp đầu tiên**, không tự cập nhật `moTa` sang giá trị mới.

Nếu không override `equals` và `hashCode` trên một lớp thông thường, hai đối tượng khác nhau có thể không được nhận diện là trùng dù mang cùng mã nghiệp vụ.

**Lưu ý:** không nên thay đổi thuộc tính tham gia vào `hashCode`/`equals` trong lúc đối tượng đang nằm trong set. Thao tác này có thể làm `contains` hoặc `remove` cho kết quả sai lệch. Các khóa dùng trong set nên ổn định hoặc bất biến.

## 7. `distinct` và `LinkedHashSet` giống và khác nhau thế nào?

Với ordered stream, `distinct()` là một phép toán trung gian loại giá trị trùng **ổn định**: giữ lần xuất hiện đầu tiên của các phần tử bằng nhau. Sau đó ta vẫn có một stream để tiếp tục các phép toán.

```java
List<String> ten = Arrays.asList(
    "Java", "Go", "Java", "Kotlin", "Go"
);

ArrayList<String> motLanMoiTen = ten.stream()
    .distinct()
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> motLanMoiTenSet = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(motLanMoiTen);
// [Java, Go, Kotlin]

System.out.println(motLanMoiTenSet);
// [Java, Go, Kotlin]
```

Hai kết quả có cùng chuỗi giá trị trong ví dụ, nhưng **kiểu dữ liệu khác nhau**:

| Cách làm | Kết quả | Khi nào phù hợp |
| --- | --- | --- |
| `distinct().collect(toCollection(ArrayList::new))` | `ArrayList<T>` không trùng theo thời điểm thu | Muốn giữ list và xử lý theo chỉ số sau đó. |
| `collect(toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` duy nhất, theo thứ tự chèn | Muốn lưu kết quả dạng set, bảo toàn thứ tự xuất hiện đầu tiên. |
| `collect(Collectors.toSet())` | `Set<T>`, không cam kết thứ tự | Chỉ cần tính duy nhất, không cần thứ tự hoặc kiểu set cụ thể. |

Không bắt buộc viết `distinct()` trước `LinkedHashSet` chỉ để loại trùng thêm một lần; điều đó thường dư thừa. Tuy nhiên, khi còn nhiều phép toán trung gian sau bước loại trùng, đặt `distinct` tại vị trí thích hợp có thể thể hiện rõ ý nghĩa pipeline.

### Thứ tự các bước có thể thay đổi kết quả

```java
List<String> ten = Arrays.asList("Kotlin", "Java", "Kotlin", "Go");

LinkedHashSet<String> a = ten.stream()
    .distinct()
    .sorted()
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = ten.stream()
    .sorted()
    .distinct()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(a); // [Go, Java, Kotlin]
System.out.println(b); // [Go, Java, Kotlin]
```

Với dữ liệu này, hai pipeline cho cùng kết quả. Nhưng nếu biến đổi giá trị khác nhau trước bước loại trùng (chẳng hạn chuẩn hóa chữ hoa/thường), hoặc sắp xếp theo khóa khác với tiêu chí bằng nhau, thứ tự và đối tượng được giữ lại có thể khác. Vì vậy, phải mô tả **muốn loại trùng trên dữ liệu gốc hay dữ liệu đã biến đổi**.

## 8. Pipeline có `filter`, `flatMap`, `sorted` và `limit`

### 8.1. `filter` giữ tương quan thứ tự các phần tử còn lại

```java
List<String> ten = Arrays.asList(
    "Java", "Go", "JavaScript", "Kotlin", "Java"
);

ArrayList<String> batDauBangJava = ten.stream()
    .filter(s -> s.startsWith("Java"))
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(batDauBangJava);
// [Java, JavaScript, Java]
```

`filter` chỉ giữ/loại, không chủ động sắp xếp. Vì nguồn có thứ tự nên thứ tự của các giá trị còn lại được bảo toàn.

### 8.2. `flatMap` nối các phần tử theo thứ tự nguồn

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("A", "B"),
    Arrays.asList("B", "C")
);

ArrayList<String> tatCa = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> duyNhat = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tatCa);  // [A, B, B, C]
System.out.println(duyNhat); // [A, B, C]
```

Với ordered stream từ hai list, kết quả của `flatMap` có thứ tự nối các stream con theo thứ tự gặp. `LinkedHashSet` vẫn chỉ giữ lần xuất hiện đầu của `"B"`.

### 8.3. `limit` áp dụng trước hay sau khi loại trùng?

```java
List<String> ten = Arrays.asList("A", "A", "B", "C", "D");

LinkedHashSet<String> a = ten.stream()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = ten.stream()
    .distinct()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(a); // [A, B]
System.out.println(b); // [A, B, C]
```

Ở `a`, ta chỉ xem ba phần tử nguồn đầu tiên rồi loại trùng; còn `b` yêu cầu ba **giá trị duy nhất** đầu tiên. Đây là khác biệt về ngữ nghĩa, nên phải đặt `limit` đúng vị trí theo yêu cầu nghiệp vụ.

## 9. Thu thập trên parallel stream có giữ thứ tự không?

**Có, nếu nguồn và pipeline có thứ tự gặp và collector được sử dụng đúng hợp đồng.** `Collectors.toCollection(ArrayList::new)` và `Collectors.toCollection(LinkedHashSet::new)` đều có thể dùng trên ordered parallel stream mà không cần tự đồng bộ hóa một collection chia sẻ.

Ví dụ Java 8:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ThuSongSong {
    public static void main(String[] args) {
        ArrayList<Integer> danhSach = IntStream.range(0, 10)
            .parallel()
            .boxed()
            .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<Integer> tapHop = IntStream.range(0, 10)
            .parallel()
            .boxed()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(danhSach);
        // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        System.out.println(tapHop);
        // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    }
}
```

`IntStream.range(0, 10)` có thứ tự gặp. Trong quá trình collect song song, triển khai có thể tạo các collection cục bộ và ghép chúng để cho kết quả phù hợp thứ tự đã cam kết. **Thứ tự phần tử trong collection kết quả không đồng nghĩa với thứ tự thực thi các lambda** trên các worker thread.

### 9.1. Vì sao không dùng `parallelStream().forEach(result::add)`?

Ví dụ sai:

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5);
ArrayList<Integer> ketQua = new ArrayList<>();

// KHÔNG AN TOÀN: nhiều luồng có thể cùng sửa ArrayList.
nguon.parallelStream().forEach(ketQua::add);
```

`ArrayList` không an toàn cho các lệnh `add` đồng thời, và `forEach` của parallel stream **không bảo đảm thứ tự gặp**. Kết quả có thể sai số phần tử, đảo thứ tự hoặc gặp lỗi khó tái hiện.

Cách đúng:

```java
ArrayList<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(ketQua); // [1, 2, 3, 4, 5]
```

`LinkedHashSet` cũng không phải cấu trúc an toàn để nhiều thread tự ý thêm phần tử đồng thời. Dùng collector thay vì tự sửa một collection chung là lựa chọn phù hợp.

### 9.2. `forEachOrdered` có thể giữ thứ tự, nhưng khác mục tiêu `collect`

`forEachOrdered` có thể thực hiện hành động theo thứ tự gặp của một ordered stream, nhưng nếu chỉ muốn **thu thành collection**, `collect` trực tiếp rõ ràng hơn và tránh quản lý trạng thái bên ngoài. Đừng dùng `forEachOrdered` như một cách thay thế mặc định cho `Collectors.toCollection`.

### 9.3. `unordered()` và nguồn không có thứ tự

```java
List<String> ten = Arrays.asList("B", "A", "C", "A");

LinkedHashSet<String> ketQua = ten.parallelStream()
    .unordered()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

`unordered()` **không bắt buộc đảo thứ tự** nhưng cho phép pipeline hoạt động không có ràng buộc thứ tự gặp. Vì thế, khi yêu cầu cần thứ tự "B, A, C" dựa trên lần xuất hiện đầu của nguồn, **đừng bỏ ràng buộc thứ tự**. Một lần chạy vẫn in `[B, A, C]` không có nghĩa sẽ luôn như vậy.

Nếu nguồn là `HashSet`, thứ tự của phần tử đến collector vốn đã không được bảo đảm:

```java
import java.util.HashSet;

HashSet<String> khongCoThuTu = new HashSet<>(
    Arrays.asList("B", "A", "C")
);

LinkedHashSet<String> ghiLaiThuTuDuyet = khongCoThuTu.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

`ghiLaiThuTuDuyet` ghi nhận thứ tự gặp **thực tế** mà nguồn cung cấp, nhưng không thể bảo đảm đó là thứ tự `"B", "A", "C"`. Nếu cần thứ tự có ý nghĩa, hãy tạo hoặc sắp xếp nguồn theo yêu cầu.

## 10. Mutability, tài nguyên và hiệu năng

Cả `ArrayList` và `LinkedHashSet` do `toCollection` tạo ra là **collection có thể sửa đổi**:

```java
ArrayList<String> ds = ten.stream()
    .collect(Collectors.toCollection(ArrayList::new));

ds.add("Rust");

LinkedHashSet<String> tap = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

tap.add("Rust");
```

Tuy nhiên, tính có thể sửa đổi không đồng nghĩa an toàn khi nhiều thread cùng thay đổi. Không dùng chúng như cấu trúc đồng thời nếu chưa có thiết kế đồng bộ hóa phù hợp.

Về tài nguyên:

- `ArrayList` lưu **mọi phần tử** nên bộ nhớ tăng theo số phần tử thu được.
- `LinkedHashSet` chỉ lưu mỗi giá trị duy nhất một lần, nhưng cần cấu trúc băm và liên kết để giữ thứ tự chèn; overhead cho mỗi phần tử có thể lớn hơn list.
- `ArrayList.contains` có độ phức tạp tuyến tính theo số phần tử; `LinkedHashSet.contains` thường có thời gian kỳ vọng gần hằng số với hàm băm tốt.
- `collect` cần tích lũy kết quả trong bộ nhớ. Nếu nguồn có thể vô hạn và không có giới hạn, thu toàn bộ bằng hai collection trên có thể không bao giờ hoàn thành hoặc hết bộ nhớ.
- `parallelStream` không tự động nhanh hơn: việc duy trì thứ tự và ghép các kết quả cục bộ có thêm chi phí.

**Không có quy tắc "`LinkedHashSet` luôn nhanh hơn `ArrayList`" hoặc ngược lại.** Chọn theo ngữ nghĩa dữ liệu trước, sau đó đo hiệu năng nếu dữ liệu lớn.

### 10.1. Nguồn vô hạn và giới hạn thu thập

```java
ArrayList<Integer> muoiSo = java.util.stream.Stream
    .iterate(1, n -> n + 1)
    .limit(10)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(muoiSo);
// [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

`limit(10)` giới hạn số phần tử được thu; bản thân `toCollection` không tạo điểm dừng cho nguồn vô hạn.

Nếu vừa muốn khử trùng vừa muốn lấy **n giá trị khác nhau**, đặt `distinct()` trước `limit(n)`; nhưng cần chắc chắn nguồn sẽ tạo đủ n giá trị khác nhau, nếu không pipeline vẫn có thể chờ mãi.

## 11. Chọn đúng collection trong ứng dụng

| Nhu cầu | Cách viết đề xuất | Lý do |
| --- | --- | --- |
| Danh sách đầy đủ theo thứ tự gặp, có thể thêm/xóa, cần `ArrayList` | `collect(toCollection(ArrayList::new))` | Giữ phần tử trùng và cam kết kiểu cụ thể. |
| Tập phần tử duy nhất theo thứ tự xuất hiện đầu | `collect(toCollection(LinkedHashSet::new))` | Duy nhất, giữ thứ tự chèn. |
| Chỉ cần một `List`, không phụ thuộc kiểu triển khai | `collect(Collectors.toList())` | Ý định đơn giản, nhưng không cam kết khả năng sửa đổi. |
| Cần list không cho phép sửa trên Java 16+ | `stream.toList()` | Trả list không cho phép sửa, giữ encounter order nếu có. |
| Chỉ cần `Set`, không quan tâm thứ tự | `collect(Collectors.toSet())` | Không cam kết thứ tự hoặc kiểu set cụ thể. |
| Cần dữ liệu duy nhất nhưng tiếp tục xử lý như list | `distinct().collect(toCollection(ArrayList::new))` | Loại trùng trong pipeline, kết quả là list. |
| Cần duy nhất theo thứ tự **sắp xếp** | `sorted().collect(toCollection(LinkedHashSet::new))` | Thứ tự gặp sau `sorted` chính là thứ tự sắp xếp. |

Trong bảng, `toCollection` là `Collectors.toCollection`. Nếu chỉ cần kết quả bất biến, hãy chọn API tương ứng theo phiên bản Java; đừng giả định `Collectors.toList()` hay `Collectors.toSet()` luôn trả collection không cho phép sửa.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Collectors.toSet()` cho thứ tự khác mong muốn | Không có bảo đảm thứ tự | Dùng `toCollection(LinkedHashSet::new)`. |
| `ArrayList` vẫn có nhiều phần tử trùng | List cho phép trùng | Dùng `LinkedHashSet` hoặc `distinct()` theo nghiệp vụ. |
| `LinkedHashSet` chỉ còn một đối tượng cho một mã | Hai đối tượng được coi bằng nhau | Kiểm tra `equals`/`hashCode` và chọn đúng tiêu chí định danh. |
| `LinkedHashSet` không xếp theo alphabet | Nó giữ thứ tự chèn, không tự sắp xếp | Dùng `sorted` trước khi thu nếu cần. |
| Nguồn `HashSet` làm kết quả thứ tự bất ổn | Nguồn không có encounter order bảo đảm | Dùng nguồn có thứ tự hoặc `sorted`. |
| `unordered()` làm mất yêu cầu giữ thứ tự | Pipeline đã bỏ ràng buộc thứ tự | Không dùng `unordered` khi thứ tự gặp quan trọng. |
| `parallelStream().forEach(list::add)` cho kết quả sai | Thao tác đồng thời lên `ArrayList` và thứ tự không bảo đảm | Dùng `collect(toCollection(ArrayList::new))`. |
| Nghĩ `Collectors.toList()` luôn là `ArrayList` | Kiểu triển khai không được cam kết | Yêu cầu rõ `toCollection(ArrayList::new)`. |
| Gọi `add` trên kết quả `Stream.toList()` bị lỗi | Kết quả Java 16+ không cho phép sửa | Dùng `toCollection(ArrayList::new)` nếu cần thêm/xóa. |
| Đối tượng trong set không tìm lại được sau khi đổi mã | Thuộc tính tham gia `hashCode` thay đổi | Dùng khóa ổn định hoặc đối tượng bất biến. |
| `limit(3)` trước khi loại trùng chỉ còn hai phần tử | Giới hạn ba đầu vào, không phải ba giá trị duy nhất | Dùng `distinct().limit(3)` nếu cần ba giá trị khác nhau. |
| Thu nguồn vô hạn gây quá tải | Không có điều kiện dừng | Giới hạn trước khi `collect`. |

## 13. Bài tập thực hành

### Bài 1 — Giữ đầy đủ hay loại trùng?

Cho:

```java
List<String> ma = Arrays.asList(
    "A01", "B02", "A01", "C03", "B02"
);
```

Hãy tạo một `ArrayList<String>` giữ nguyên tất cả mã, đồng thời tạo `LinkedHashSet<String>` chứa mỗi mã một lần theo thứ tự xuất hiện đầu tiên. Dự đoán hai kết quả.

### Bài 2 — Chuẩn hóa trước khi khử trùng

Cho:

```java
List<String> ngonNgu = Arrays.asList(
    " Java ", "java", "Go", " GO ", "Kotlin"
);
```

Viết pipeline để loại khoảng trắng thừa, chuyển sang chữ thường bằng `Locale.ROOT` rồi thu thành `LinkedHashSet<String>`. Kết quả có những giá trị nào và thứ tự ra sao?

### Bài 3 — Giới hạn trước hay sau khi loại trùng?

Cho:

```java
List<Integer> so = Arrays.asList(1, 1, 2, 3, 4);
```

Hãy tìm kết quả của:

```java
LinkedHashSet<Integer> x = so.stream()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

ArrayList<Integer> y = so.stream()
    .distinct()
    .limit(3)
    .collect(Collectors.toCollection(ArrayList::new));
```

### Bài 4 — Song song và thứ tự

Một danh sách `["A", "B", "A", "C"]` cần được thu thành set theo thứ tự xuất hiện đầu. Chọn giữa `Collectors.toSet()` và `Collectors.toCollection(LinkedHashSet::new)`. Nếu chuyển `stream()` thành `parallelStream()` trên nguồn list có thứ tự, cách đã chọn có còn bảo đảm thứ tự kết quả không?

### Bài 5 — Chọn cách giữ đối tượng đầu tiên

Danh sách bản ghi có cùng mã `"X01"` nhưng hai mô tả khác nhau; cần giữ **bản xuất hiện đầu**. Cần lưu ý gì về `equals`, `hashCode` và việc sửa mã sau khi đưa vào `LinkedHashSet`?

### Đáp án tham khảo

**Bài 1:**

```java
ArrayList<String> tatCa = ma.stream()
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> duyNhat = ma.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tatCa);   // [A01, B02, A01, C03, B02]
System.out.println(duyNhat); // [A01, B02, C03]
```

**Bài 2:**

```java
LinkedHashSet<String> chuanHoa = ngonNgu.stream()
    .map(String::trim)
    .map(s -> s.toLowerCase(java.util.Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(chuanHoa); // [java, go, kotlin]
```

Chuỗi `" Java "` đứng trước nên tạo khóa `"java"` đầu tiên; các lần lặp lại bị loại.

**Bài 3:** `x = [1, 2]` vì ba phần tử đầu là `1, 1, 2`. `y = [1, 2, 3]` vì `distinct` loại bản sao trước khi `limit(3)` đếm ba giá trị duy nhất.

**Bài 4:** dùng `Collectors.toCollection(LinkedHashSet::new)` để bảo đảm kiểu set và thứ tự chèn theo encounter order. Với ordered stream từ `List`, phép thu đúng hợp đồng này vẫn bảo toàn thứ tự kết quả khi xử lý song song. Không tự chèn vào một `LinkedHashSet` dùng chung bằng `parallelStream().forEach`.

**Bài 5:** cần quy định tính bằng nhau dựa trên mã và triển khai `equals`/`hashCode` nhất quán. `LinkedHashSet` giữ đối tượng gặp trước, không tự hợp nhất mô tả. Mã dùng cho băm cần ổn định trong suốt thời gian đối tượng nằm trong set.

## 14. Ghi nhớ

```java
// Giữ đầy đủ, có thể trùng, theo thứ tự gặp:
ArrayList<T> list = stream
    .collect(Collectors.toCollection(ArrayList::new));

// Giữ duy nhất, theo thứ tự xuất hiện đầu:
LinkedHashSet<T> set = stream
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

Hai dòng trên là **mẫu minh họa generic**: trong chương trình thực tế, thay `T` và `stream` bằng kiểu/biến cụ thể.

Để kết quả thực sự có thứ tự mong muốn, nguồn hoặc pipeline phải có **encounter order** có ý nghĩa. `ArrayList` giữ trùng, `LinkedHashSet` loại trùng dựa vào `equals`/`hashCode` và nhớ thứ tự chèn; cả hai là collection có thể sửa nhưng không nên dùng làm nơi cập nhật chung cho nhiều thread. Với pipeline song song, dùng collector đúng hợp đồng để thu kết quả và chú ý chi phí duy trì thứ tự.

Hiểu rõ khác biệt này giúp lựa chọn kết quả phù hợp, tránh lỗi mất dữ liệu hoặc đảo thứ tự khi kết hợp `filter`, `map`, `collect` và các pipeline Stream API nâng cao.
