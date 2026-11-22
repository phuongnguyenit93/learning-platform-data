# Giới hạn null và hợp đồng comparator trong skip list đồng thời

## 1. Hai điều kiện nền tảng của dữ liệu có thứ tự

`ConcurrentSkipListMap` và `ConcurrentSkipListSet` hỗ trợ truy cập đồng thời, nhưng khả năng đó không thay thế các quy tắc của dữ liệu đầu vào.

Có hai câu hỏi cần trả lời trước khi dùng:

1. Có được lưu null không, và null trả về từ API có nghĩa gì?
2. Phép so sánh có tạo ra một thứ tự hợp lệ, ổn định và phù hợp với tính duy nhất của khóa/phần tử không?

Nếu hiểu sai null, chương trình có thể nhầm “không có kết quả” với một giá trị đã lưu. Nếu comparator sai, việc tìm kiếm, xác định trùng và truy vấn khoảng không còn diễn đạt đúng yêu cầu.

Các quy tắc trong bài áp dụng cho Java hiện hành; ví dụ chạy bằng Java 17+.

## 2. Không lưu khóa, giá trị hoặc phần tử null

| Cấu trúc | Dữ liệu không được null |
| --- | --- |
| `ConcurrentSkipListMap<K,V>` | Khóa K và giá trị V |
| `ConcurrentSkipListSet<E>` | Phần tử E |

Ví dụ map từ số sang chuỗi không thể lưu `null -> "A"` hoặc `10 -> null`. Tập hợp chuỗi cũng không thể thêm phần tử null.

Một mục đích của giới hạn này là giữ rõ ý nghĩa của các kết quả null biểu thị không có ánh xạ hoặc không có phần tử phù hợp trong bối cảnh truy cập đồng thời. Xem [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) và [ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

### Comparator.nullsFirst không gỡ giới hạn của collection

`Comparator.nullsFirst(...)` tạo một phép so sánh biết xử lý null. Nhưng **khả năng so sánh null** và **quyền lưu null của cấu trúc** là hai hợp đồng khác nhau.

Một `ConcurrentSkipListMap` dùng comparator như vậy vẫn từ chối khóa null; `ConcurrentSkipListSet` vẫn từ chối phần tử null. Không suy từ một cách cấu hình comparator của collection khác rằng skip list đồng thời cũng có cùng quyền lưu dữ liệu.

### comparator() trả null có nghĩa khác

Nếu dùng thứ tự tự nhiên, `map.comparator()` hoặc `set.comparator()` trả null để biểu thị **không có comparator riêng**. Điều này không nói rằng cấu trúc đang chứa null hoặc đã cho phép null.

Thứ tự tự nhiên do kiểu dữ liệu cung cấp qua `Comparable`, ví dụ thứ tự số của `Integer` và thứ tự từ điển của `String`. Xem [Comparable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html).

## 3. Null trả về không đồng nghĩa null được lưu

Với map không lưu giá trị null, `get(key)` trả null nghĩa là không có ánh xạ cho khóa tại phép đọc đó. `floorKey/ceilingKey` trả null khi không có khóa đáp ứng điều kiện.

Một số API dùng null làm **tín hiệu điều khiển** thay vì dữ liệu cần lưu:

- `computeIfAbsent(k, function)`: nếu hàm trả null, không thiết lập ánh xạ mới cho lời gọi đó.
- `computeIfPresent(k, function)`: nếu hàm cập nhật trả null, ánh xạ hiện có được loại bỏ theo hợp đồng.
- `putIfAbsent(k, v)`: trả null khi trước đó không có ánh xạ và lời gọi chèn được v.

Như vậy “không lưu null” không có nghĩa mọi kết quả null hoặc mọi hàm trả null đều gây lỗi. Cần đọc hợp đồng **từng phương thức**, không dùng một khẩu quyết áp dụng cho tất cả tham số. Xem [các phương thức cập nhật ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Nếu dữ liệu nghiệp vụ cần phân biệt “chưa có ánh xạ” với “đã xác định là không có kết quả”, hãy mô hình hóa bằng một giá trị khác null có ý nghĩa rõ, chẳng hạn một kiểu trạng thái. Không cố đưa null vào map để biểu diễn cả hai trạng thái.

Trong mã nhiều luồng, một kết quả get là quan sát của thao tác đó; nó không giữ nguyên map cho các thao tác tiếp theo. Muốn cập nhật theo điều kiện, dùng API phù hợp như `putIfAbsent` hoặc `replace(expected,...)`.

## 4. Comparator quyết định thứ tự và việc trùng khóa

Map sắp xếp các **khóa**, còn set sắp xếp các **phần tử**. Mỗi lời gọi comparator trả:

- Số âm: đối số thứ nhất đứng trước đối số thứ hai.
- 0: hai đối số bằng nhau theo phép so sánh.
- Số dương: đối số thứ nhất đứng sau.

Không bắt buộc chỉ trả đúng -1, 0 hoặc 1; điều quan trọng là dấu và các quan hệ phải đúng.

Trong cấu trúc có thứ tự, kết quả 0 cũng quyết định việc hai khóa/phần tử được xem là trùng theo thứ tự. Ví dụ comparator chỉ so sánh độ dài String sẽ xem `"cat"` và `"dog"` là bằng nhau dù hai chuỗi không `equals`.

Với map dùng comparator ấy, put giá trị cho "dog" có thể cập nhật ánh xạ cùng lớp so sánh với "cat", thay vì tạo khóa riêng. Với set, thêm chuỗi thứ hai cùng độ dài không giữ được cả hai như một danh sách.

Comparator cần nhất quán với `equals` để cấu trúc tuân thủ đầy đủ hợp đồng tổng quát của Map/Set. Đây là điểm phải thiết kế chủ động, không phải lỗi mà khả năng đồng thời của collection sẽ tự sửa. Xem [Comparator: consistency with equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html).

## 5. Các tính chất comparator phải giữ

Gọi `c(x,y)` là kết quả so sánh và `sign` là dấu của kết quả.

### Đảo đối số phải đảo dấu

```text
sign(c(x,y)) = -sign(c(y,x))
```

Nếu x đứng trước y thì y phải đứng sau x. Với chính nó, một giá trị hợp lệ phải so sánh bằng 0.

### Quan hệ phải bắc cầu

Nếu x lớn hơn y theo comparator và y lớn hơn z, x phải lớn hơn z. Không tạo quy tắc kiểu x trước y, y trước z nhưng z lại trước x.

### Bằng nhau theo so sánh phải có quan hệ nhất quán với phần tử thứ ba

Nếu `c(x,y) == 0`, thì dấu của `c(x,z)` và `c(y,z)` phải giống nhau với mọi z hợp lệ. Không thể vừa xem x và y là một vị trí thứ tự, vừa để chúng đứng ở hai phía khác nhau của z.

Các yêu cầu chính xác thuộc [hợp đồng Comparator.compare](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html). Chúng cần đúng trên toàn miền dữ liệu được phép, không chỉ trên vài cặp dễ kiểm thử.

Ngoài ra, các khóa/phần tử đang cùng một cấu trúc phải so sánh được với nhau. Khai báo một kiểu tổng quát quá rộng không tạo ra quy tắc hợp lệ để so sánh tùy ý `Integer`, `String` và các đối tượng khác.

## 6. Chương trình đầy đủ chạy trên Java 17+

Ví dụ kiểm tra từng hợp đồng trong một luồng để kết quả rõ ràng; đây không phải bài đo hiệu năng hoặc kiểm thử lịch chạy đa luồng.

Tệp `SkipListNullAndComparator.java`:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentSkipListSet;

public class SkipListNullAndComparator {
    private static void expectNullError(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": missing exception");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();
        map.put(10, "A");
        System.out.println("natural comparator=" + map.comparator());
        System.out.println("missing get=" + map.get(99));
        expectNullError("null key", () -> map.put(null, "B"));
        expectNullError("null value", () -> map.put(20, null));
        expectNullError("null search key", () -> map.floorKey(null));

        Comparator<String> nullAware =
                Comparator.nullsFirst(Comparator.naturalOrder());
        ConcurrentSkipListMap<String, Integer> nullAwareMap =
                new ConcurrentSkipListMap<>(nullAware);
        ConcurrentSkipListSet<String> nullAwareSet =
                new ConcurrentSkipListSet<>(nullAware);
        expectNullError("null-aware map key",
                () -> nullAwareMap.put(null, 1));
        expectNullError("null-aware set element",
                () -> nullAwareSet.add(null));

        System.out.println("compute absent null="
                + map.computeIfAbsent(20, key -> null));
        System.out.println("contains 20=" + map.containsKey(20));
        System.out.println("compute present null="
                + map.computeIfPresent(10, (key, oldValue) -> null));
        System.out.println("contains 10=" + map.containsKey(10));

        Comparator<String> byLength = Comparator.comparingInt(String::length);
        ConcurrentSkipListMap<String, Integer> collapsed =
                new ConcurrentSkipListMap<>(byLength);
        collapsed.put("cat", 1);
        System.out.println("equal-length previous=" + collapsed.put("dog", 2));
        System.out.println("equal-length size=" + collapsed.size());
        System.out.println("equal-length get cat=" + collapsed.get("cat"));

        Comparator<String> lengthThenText =
                byLength.thenComparing(Comparator.naturalOrder());
        ConcurrentSkipListSet<String> distinct =
                new ConcurrentSkipListSet<>(lengthThenText);
        distinct.add("dog");
        distinct.add("cat");
        System.out.println("length-and-text set=" + distinct);

        Comparator<Integer> unsafe = (a, b) -> a - b;
        Comparator<Integer> safe = Integer::compare;
        System.out.println("unsafe compare MIN vs 1="
                + unsafe.compare(Integer.MIN_VALUE, 1));
        System.out.println("safe compare MIN vs 1="
                + safe.compare(Integer.MIN_VALUE, 1));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 SkipListNullAndComparator.java
java SkipListNullAndComparator
```

Kết quả chính xác:

```text
natural comparator=null
missing get=null
null key=NullPointerException
null value=NullPointerException
null search key=NullPointerException
null-aware map key=NullPointerException
null-aware set element=NullPointerException
compute absent null=null
contains 20=false
compute present null=null
contains 10=false
equal-length previous=1
equal-length size=1
equal-length get cat=2
length-and-text set=[cat, dog]
unsafe compare MIN vs 1=2147483647
safe compare MIN vs 1=-1
```

## 7. Đọc các kết quả quan trọng

### Lỗi null được kiểm tra đúng loại

Hàm `expectNullError` chỉ chấp nhận `NullPointerException` ở những lời gọi được kiểm tra. Nếu lời gọi không lỗi, chương trình ném `AssertionError`; nó không coi mọi ngoại lệ là “đúng”.

Map có comparator xử lý null vẫn không chèn được khóa null; set cùng comparator vẫn không thêm được null. Điều đó tách rõ hợp đồng comparator khỏi hợp đồng lưu trữ.

### Null từ hàm cập nhật không trở thành một giá trị lưu trữ

`computeIfAbsent(20, key -> null)` trả null nhưng khóa 20 không được chèn. `computeIfPresent(10, ... -> null)` làm khóa 10 bị xóa.

Hai lời gọi minh họa tín hiệu API. Không suy rằng các callback của `ConcurrentSkipListMap` luôn chạy đúng một lần khi có tranh chấp; ví dụ dùng hàm không có tác động phụ và không dựa vào số lần gọi.

### So sánh chỉ theo độ dài làm hai String bị xem là cùng một khóa

Sau khi put "cat" với giá trị 1, put "dog" với giá trị 2 trả về giá trị cũ 1. Map chỉ có một ánh xạ theo thứ tự đó, và tra bằng "cat" nhận 2.

Nếu mục tiêu là giữ cả hai chuỗi, comparator chỉ theo độ dài chưa phù hợp. Ví dụ bổ sung thứ tự tự nhiên khi độ dài bằng nhau:

```java
Comparator<String> lengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

Khi đó "cat" và "dog" được phân biệt, set giữ cả hai theo thứ tự `[cat, dog]`. Với String trong ví dụ, quy tắc này nhất quán với equals.

Không thêm một tiêu chí phụ tùy tiện chỉ để làm mọi đối tượng khác tham chiếu thành khác nhau: tiêu chí phải phù hợp với danh tính nghiệp vụ và `equals` của kiểu dữ liệu.

## 8. Không trừ hai số để viết comparator

Mã sau trông ngắn nhưng có thể tràn số:

```java
Comparator<Integer> unsafe = (a, b) -> a - b;
```

Trong ví dụ, `Integer.MIN_VALUE` nhỏ hơn 1. Tuy nhiên `MIN_VALUE - 1` tràn thành số dương 2.147.483.647, nên comparator báo dấu ngược với thứ tự số mong muốn.

Dùng API so sánh phù hợp:

```java
Comparator<Integer> safe = Integer::compare;
```

Với trường int của đối tượng, có thể dùng `Comparator.comparingInt(...)`; với long, dùng `Long.compare` hoặc `comparingLong`. Nếu cần đảo chiều, dùng `reversed()` thay vì tự đổi dấu bằng phép toán có nguy cơ tràn.

Bộ kiểm thử chỉ dùng dữ liệu nhỏ có thể không phát hiện lỗi tràn. Cần thêm các giá trị biên như MIN_VALUE, MAX_VALUE, 0 và các cặp khác dấu.

Không đưa comparator vi phạm hợp đồng vào collection rồi kỳ vọng một lỗi cụ thể luôn được ném. Dữ liệu có thể cho kết quả không phản ánh thứ tự mong muốn; collection không cam kết phát hiện mọi sai sót của comparator.

## 9. Giữ thứ tự ổn định khi có nhiều luồng

### Không sửa các trường quyết định thứ tự khi đối tượng còn trong cấu trúc

Nếu khóa có trường `priority` và comparator đọc trường ấy, thay priority trực tiếp sau khi chèn không tự di chuyển khóa tới vị trí mới.

Trong mã nhiều luồng, việc sửa như vậy còn làm các lần so sánh quan sát trạng thái khác nhau. Collection đồng thời bảo vệ thao tác trên cấu trúc; nó không tái lập một thứ tự hợp lệ cho khóa bị thay đổi tùy ý.

Thường nên dùng khóa bất biến. Nếu nghiệp vụ cần đổi thuộc tính sắp xếp, hãy thiết kế rõ bước xóa/chèn lại hoặc một mô hình dữ liệu khác; cả chuỗi đó vẫn cần được đánh giá về tính nguyên tử theo yêu cầu.

### Comparator không nên phụ thuộc trạng thái thay đổi bên ngoài

Tránh phép so sánh dựa trên một cờ đổi chiều đang bị luồng khác bật/tắt, giờ hiện tại hoặc trạng thái ngẫu nhiên. Cùng một cặp khóa không thể lúc đứng trước, lúc đứng sau mà vẫn duy trì cấu trúc đã sắp xếp.

Comparator có thể bị nhiều luồng gọi. Nếu có trạng thái dùng chung bên trong, chính comparator cũng cần an toàn khi được sử dụng đồng thời. Một comparator không giữ trạng thái, chỉ đọc dữ liệu bất biến thường dễ kiểm tra hơn.

### Chi phí so sánh ảnh hưởng chi phí thao tác

Phép so sánh có thể được gọi nhiều lần trong tìm kiếm hoặc cập nhật. Tránh để comparator thực hiện truy cập chậm, tác động bên ngoài hoặc phụ thuộc dữ liệu chưa ổn định.

Đây là yêu cầu thiết kế của hàm so sánh, không phải lý do để bỏ qua kiểm tra tính đúng đắn nhằm tối ưu sớm.

## 10. Những sự nhầm lẫn cần tránh

- `comparator() == null` biểu thị thứ tự tự nhiên, không phải quyền lưu null.
- Comparator xử lý null không làm `ConcurrentSkipListMap/Set` chấp nhận null.
- Một giá trị trả null từ API có thể là tín hiệu không có kết quả hoặc quy tắc cập nhật; không nhất thiết là lỗi.
- `compare(x,y) == 0` ảnh hưởng tính duy nhất của khóa/phần tử, không chỉ cách hiển thị.
- So sánh đúng trên dữ liệu nhỏ chưa chứng minh không tràn số hoặc bắc cầu đúng.
- Cấu trúc đồng thời không sửa được comparator phụ thuộc trạng thái thay đổi hoặc khóa có thuộc tính thứ tự bị sửa trực tiếp.

## 11. Kiểm thử và thực hành

1. Viết ca xác nhận khóa null, giá trị null và phần tử null bị từ chối, kể cả khi dùng `nullsFirst`.
2. Kiểm tra riêng null trả về từ tìm kiếm vắng và null trả về từ hàm cập nhật; đối chiếu khóa có tồn tại sau lời gọi hay không.
3. Với comparator tùy chỉnh, kiểm tra dấu khi đảo đối số, tính bắc cầu trên các bộ ba và quan hệ bằng 0 với phần tử thứ ba.
4. Tạo hai đối tượng bằng nhau theo equals và hai đối tượng khác nhau; xác định comparator có cùng cách phân biệt không.
5. Thêm dữ liệu có cùng tiêu chí chính nhưng khác tiêu chí phụ, kiểm tra có giữ đúng số phần tử theo yêu cầu.
6. Kiểm thử các giá trị số biên, không chỉ các số liên tiếp nhỏ.
7. Với kiểu nghiệp vụ dùng làm khóa, xác nhận những trường tham gia so sánh không bị thay đổi khi khóa vẫn nằm trong cấu trúc.

Bài tập: thay comparator chỉ theo độ dài bằng “độ dài giảm dần, rồi thứ tự chữ tăng dần”. Dự đoán vị trí của "ant", "dog" và "horse", sau đó kiểm tra các truy vấn floor/ceiling theo chính thứ tự ấy. Giải thích vì sao việc đảo chiều tiêu chí chính không cho phép bỏ các yêu cầu bắc cầu và nhất quán với equals.
