# Kết hợp wildcard với nhiều tham số kiểu

## 1. Vì sao một dấu hỏi thường không đủ?

Một cấu trúc dữ liệu có thể mang nhiều vai trò kiểu khác nhau. `Map<K, V>` chứa khóa kiểu `K` và giá trị kiểu `V`. Một phép biến đổi có thể nhận thêm kiểu kết quả `R`. Khi thiết kế phương thức tổng quát, cần xác định riêng từng vai trò:

- Ta đọc khóa hay ghi khóa?
- Ta đọc giá trị hay ghi giá trị?
- Hàm được truyền vào nhận những kiểu gì và trả về kiểu gì?
- Các vị trí nào phải liên hệ với nhau qua cùng một tham số kiểu?

Wildcard không thay thế toàn bộ suy luận này. Nó chỉ biểu diễn **một kiểu chưa biết tại một vị trí đối số kiểu**. Mỗi vị trí được chọn cận riêng theo nhu cầu sử dụng.

Ví dụ, phương thức sao chép các cặp khóa–giá trị có thể có hợp đồng:

```java
static <K, V> void copyMappings(
        Map<? extends K, ? extends V> source,
        Map<? super K, ? super V> destination) {
    source.forEach((key, value) -> destination.put(key, value));
}
```

Nguồn cung cấp cả khóa lẫn giá trị, nên cả hai vị trí dùng `extends`. Đích nhận cả hai, nên cả hai vị trí dùng `super`. Các tên `K` và `V` nối tương ứng khóa với khóa, giá trị với giá trị giữa hai tham số.

Những đoạn ngắn trong bài là mã minh họa trong một lớp hoặc phương thức thích hợp. Chương trình ở mục 6 có đủ import và có thể chạy độc lập trên Java 17+. Quy tắc wildcard vẫn là cơ chế generics được đưa vào từ Java 5; ví dụ có hàm lambda dùng API Java hiện đại.

## 2. Phân biệt tham số kiểu có tên và wildcard

### 2.1. Tên kiểu giữ một quan hệ; wildcard che một kiểu

Trong `<K, V>`, `K` và `V` là các tham số kiểu do phương thức khai báo. Chúng có thể xuất hiện nhiều lần để biểu đạt những quan hệ cần giữ.

Trong `Map<?, ?>`, hai dấu `?` là hai kiểu chưa biết **độc lập**:

```java
Map<?, ?> unknown = Map.of("count", 3);

Object key = unknown.keySet().iterator().next();
Object value = unknown.get(key);

// unknown.put(key, value); // Không biên dịch.
```

Đọc được hai đối tượng kiểu `Object` không chứng minh chúng có kiểu chính xác mà `put` yêu cầu. `Map.get` nhận `Object`, nên lời gọi `get(key)` không giúp khôi phục quan hệ kiểu đã mất.

Hai dấu hỏi không có nghĩa khóa và giá trị cùng kiểu. `Map<String, Integer>` hoàn toàn phù hợp với `Map<?, ?>`.

Nếu một thuật toán cần gọi tên riêng hai kiểu để dùng lại, khai báo `<K, V>`; nếu cần biểu đạt cùng một kiểu ở hai vị trí, dùng cùng một tên:

```java
static <T> void moveFirst(List<T> source, List<T> destination) {
    destination.add(source.get(0));
}
```

Ví dụ trên chỉ minh họa quan hệ kiểu, giả định nguồn có phần tử và đích cho phép thêm. Hai tham số `List<T>` giữ cùng đối số kiểu `T`. Hai tham số `List<?>` sẽ không hứa điều đó.

Tuy nhiên, nếu chỉ cần lấy phần tử từ nguồn và thêm vào đích, có thể thiết kế linh hoạt hơn bằng `List<? extends T>` và `List<? super T>`. Mức độ ràng buộc phải xuất phát từ thao tác thật sự của thuật toán.

### 2.2. Cận thuộc về từng vị trí

Các kiểu sau có hợp đồng khác nhau:

| Kiểu tham số | Khóa khi đọc | Giá trị khi đọc | Có thể `put` khóa `K` và giá trị `V` không? |
| --- | --- | --- | --- |
| `Map<K, V>` | `K` | `V` | Có |
| `Map<K, ? extends V>` | `K` | `V` | Không bảo đảm đối số giá trị được chấp nhận |
| `Map<? extends K, V>` | `K` | `V` | Không bảo đảm đối số khóa được chấp nhận |
| `Map<? extends K, ? extends V>` | `K` | `V` | Không bảo đảm cả hai |
| `Map<? super K, ? super V>` | `Object` | `Object` | Có |
| `Map<?, ?>` | `Object` | `Object` | Không có kiểu cụ thể nào được bảo đảm |

Cột đọc mô tả kiểu an toàn của khóa khi duyệt và của giá trị nhận từ map. `get` vẫn có thể trả `null` nếu không có ánh xạ tương ứng hoặc map lưu giá trị `null`.

“Có” trong cột `put` chỉ nói rằng trình biên dịch chấp nhận các đối số theo kiểu tĩnh. Nó chưa bảo đảm map hỗ trợ sửa đổi hoặc chấp nhận `null`.

Bảng cũng cho thấy không nên máy móc đặt mọi đối số kiểu thành cùng một loại wildcard. Nếu thuật toán cần giữ chính xác kiểu khóa nhưng chỉ đọc giá trị, `Map<K, ? extends V>` có thể phù hợp hơn.

## 3. Áp dụng PECS riêng cho từng kiểu

PECS viết tắt của “Producer Extends, Consumer Super”: nơi cung cấp giá trị dùng cận trên; nơi nhận giá trị dùng cận dưới. Hãy áp dụng cho từng luồng dữ liệu.

Với `copyMappings`:

```text
source cung cấp khóa    → K → destination nhận khóa
source cung cấp giá trị → V → destination nhận giá trị
```

Ví dụ lời gọi:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
Map<CharSequence, Number> widened = new LinkedHashMap<>();

copyMappings(scores, widened);
```

Có thể xét `K = String`, `V = Integer`:

- `Map<String, Integer>` đáp ứng `Map<? extends String, ? extends Integer>`.
- `CharSequence` là kiểu cha của `String`, nên đích đáp ứng vị trí `? super String`.
- `Number` là kiểu cha của `Integer`, nên đích đáp ứng vị trí `? super Integer`.

Quan hệ giữa khóa và giá trị được kiểm tra riêng. Không cần `K` và `V` có quan hệ kế thừa với nhau.

### 3.1. Một vị trí không tương thích làm cả lời gọi thất bại

```java
Map<String, Integer> source = new LinkedHashMap<>();

Map<String, Number> byValue = new LinkedHashMap<>();
copyMappings(source, byValue); // Hợp lệ.

Map<Object, Object> general = new LinkedHashMap<>();
copyMappings(source, general); // Hợp lệ.

Map<String, Double> wrongValue = new LinkedHashMap<>();
// copyMappings(source, wrongValue); // Không biên dịch.

Map<Integer, Number> wrongKey = new LinkedHashMap<>();
// copyMappings(source, wrongKey); // Không biên dịch.
```

Trong hai dòng bị cấm, đích lần lượt không nhận được `Integer` ở vị trí giá trị hoặc không nhận được `String` ở vị trí khóa. Thêm wildcard không biến một phép chuyển đổi dữ liệu tùy ý thành hợp lệ.

### 3.2. Vì sao không chỉ dùng Map<K, V> cho mọi vị trí?

Nếu khai báo:

```java
static <K, V> void copyExact(Map<K, V> source,
                              Map<K, V> destination) {
    destination.putAll(source);
}
```

thì `Map<String, Integer>` và `Map<CharSequence, Number>` không thể đồng thời khớp cùng hai đối số kiểu của hai tham số `Map<K, V>`. `Map` bất biến theo đối số kiểu; quan hệ `String <: CharSequence` và `Integer <: Number` không tự lan thành quan hệ gán giữa hai kiểu map cụ thể.

Phiên bản có wildcard cho phép những kiểu cụ thể khác nhau trong khi vẫn kiểm tra đúng các luồng dữ liệu.

## 4. Thêm tham số kiểu kết quả và hàm nhận hai đầu vào

Xét một phương thức biến mỗi cặp khóa–giá trị thành một kết quả:

```java
static <K, V, R> List<R> mapEntries(
        Map<? extends K, ? extends V> source,
        BiFunction<? super K, ? super V, ? extends R> mapper) {
    List<R> result = new ArrayList<>();

    source.forEach((key, value) ->
            result.add(mapper.apply(key, value)));

    return result;
}
```

Đọc chữ ký theo luồng:

1. `source` cung cấp khóa dùng được như `K` và giá trị dùng được như `V`.
2. `mapper` nhận khóa và giá trị, nên hai đầu vào là `? super K` và `? super V`.
3. `mapper` cung cấp một kết quả dùng được như `R`, nên đầu ra là `? extends R`.
4. Phương thức tự tạo danh sách kết quả với kiểu phần tử đã đặt tên là `R`, nên trả `List<R>`.

Không cần trả `List<? extends R>` chỉ vì tham số có wildcard. Một kiểu trả về cụ thể thường giúp nơi gọi sử dụng kết quả thuận tiện hơn khi phương thức có thể cung cấp hợp đồng đó.

Ví dụ hàm nhận kiểu rộng hơn dữ liệu nguồn:

```java
BiFunction<CharSequence, Number, String> format =
        (name, score) -> name + "=" + score.intValue();

List<String> labels = mapEntries(scores, format);
```

Hàm này xử lý được một `CharSequence` và một `Number`, nên cũng xử lý được các khóa `String` và giá trị `Integer` từ `scores`.

Có thể chọn kết quả tổng quát hơn:

```java
List<CharSequence> labelsAsText =
        MultiWildcardDemo.<String, Integer, CharSequence>
                mapEntries(scores, format);
```

Đây là cú pháp gọi với đối số kiểu tường minh, giả sử các phương thức nằm trong lớp `MultiWildcardDemo`. Kiểu trả về của `format` là `String`, một kiểu con của `CharSequence`, nên khớp `? extends R`.

Các đối số kiểu tường minh hữu ích khi học cách đối chiếu hợp đồng. Thông thường, hãy để trình biên dịch suy luận từ đối số và ngữ cảnh sử dụng; không cần viết lại chúng ở mọi lời gọi.

## 5. Wildcard lồng nhau: phải kiểm tra từng lớp bao

Có nhiều tham số kiểu và có nhiều tầng kiểu là hai vấn đề khác nhau. Với một danh sách các cặp khóa–giá trị:

```java
List<Map.Entry<String, Integer>> entries = new ArrayList<>();
```

ta có thể muốn nhận mọi cặp có khóa dùng được như `CharSequence`, giá trị dùng được như `Number`.

Chỉ thêm wildcard bên trong `Map.Entry` chưa đủ:

```java
// Không biên dịch:
// List<Map.Entry<? extends CharSequence, ? extends Number>> bad = entries;

List<? extends Map.Entry<? extends CharSequence, ? extends Number>> good =
        entries;
```

Lý do: dù một `Map.Entry<String, Integer>` phù hợp với kiểu cặp có hai cận trên, `List` ở lớp ngoài vẫn bất biến. Nếu phép gán `bad` được phép, nó có thể cho thêm một cặp `Map.Entry<StringBuilder, Double>` vào danh sách chỉ chứa `Map.Entry<String, Integer>`.

Wildcard cận trên ở lớp `List` ngăn việc thêm một cặp tùy ý và cho phép góc nhìn đọc cần thiết.

Ví dụ một hàm chỉ đọc:

```java
static double totalValues(
        List<? extends Map.Entry<?, ? extends Number>> entries) {
    double total = 0.0;
    for (Map.Entry<?, ? extends Number> entry : entries) {
        total += entry.getValue().doubleValue();
    }
    return total;
}
```

Ở đây:

- Khóa không tham gia thuật toán, nên dùng `?`.
- Giá trị cần đọc như `Number`, nên dùng `? extends Number`.
- Danh sách ngoài cung cấp các cặp, nên dùng `? extends Map.Entry<...>`.

Ví dụ giả định các cặp và giá trị không `null`. Không cần thêm `K` chỉ để đặt tên cho kiểu khóa không bao giờ được dùng.

## 6. Chương trình hoàn chỉnh

Lưu thành `MultiWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;

public class MultiWildcardDemo {
    static <K, V> void copyMappings(
            Map<? extends K, ? extends V> source,
            Map<? super K, ? super V> destination) {
        source.forEach((key, value) -> destination.put(key, value));
    }

    static <K, V, R> List<R> mapEntries(
            Map<? extends K, ? extends V> source,
            BiFunction<? super K, ? super V, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        source.forEach((key, value) ->
                result.add(mapper.apply(key, value)));
        return result;
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("Ada", 9);
        scores.put("Linh", 10);

        Map<CharSequence, Number> widened = new LinkedHashMap<>();
        copyMappings(scores, widened);

        BiFunction<CharSequence, Number, String> format =
                (name, score) -> name + "=" + score.intValue();

        List<String> labels = mapEntries(scores, format);

        List<CharSequence> text =
                MultiWildcardDemo.<String, Integer, CharSequence>
                        mapEntries(scores, format);

        System.out.println("copied = " + widened);
        System.out.println("labels = " + labels);
        System.out.println("text = " + text);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all MultiWildcardDemo.java
java MultiWildcardDemo
```

Stdout chính xác:

```text
copied = {Ada=9, Linh=10}
labels = [Ada=9, Linh=10]
text = [Ada=9, Linh=10]
```

`LinkedHashMap` giữ thứ tự thêm khóa, nên các dòng trên có thứ tự xác định. Dùng `HashMap` thay thế thì không được mặc định dự đoán cùng thứ tự khi duyệt.

`copyMappings` thêm từng ánh xạ vào đích; nếu đích đã có khóa tương đương, giá trị cũ được thay. Đây là sao chép các tham chiếu khóa và giá trị, không phải sao chép sâu đối tượng. Các hàm minh họa cũng không cung cấp tính nguyên tử hay khả năng hoàn tác nếu một thao tác ném ngoại lệ giữa chừng.

## 7. Những lỗi dễ gặp

### 7.1. Dùng cùng một dấu hỏi như thể đó là tên kiểu

```java
static void cannotCopy(Map<?, ?> source, Map<?, ?> destination) {
    // source.forEach((key, value) -> destination.put(key, value));
    // Không biên dịch: các kiểu bị che của đích không liên hệ với nguồn.
}
```

Giải pháp là đặt tên các quan hệ cần giữ bằng `<K, V>`, rồi dùng wildcard để mở rộng phạm vi đối số một cách an toàn như `copyMappings`.

### 7.2. Đặt sai chiều wildcard cho hàm xử lý

`BiFunction<? extends K, ? extends V, ? super R>` không phù hợp với thuật toán ở mục 4:

- Hàm có thể chỉ nhận một kiểu con hẹp hơn `K`; ta không thể truyền một `K` bất kỳ vào.
- Tương tự với đầu vào `V`.
- Kết quả là một kiểu cha chưa biết của `R`, nên không thể bảo đảm đọc thành `R`.

Hãy phân tích từng đầu vào và đầu ra của chính hàm xử lý, không chọn `extends` chỉ vì “đây là tham số đầu vào của phương thức ngoài”.

### 7.3. Dùng wildcard trong nơi khai báo tên tham số kiểu

```java
// Sai cú pháp:
// static <? extends Number, V> void process(...) { }
```

Khai báo tham số kiểu cần có tên, ví dụ `<K extends Number, V>`. Wildcard xuất hiện ở vị trí **đối số kiểu**, chẳng hạn `Map<? extends Number, V>`.

Cũng không thể viết `? extends K & V` để đòi hai cận cùng lúc. Nếu cần cận giao phù hợp, khai báo một tham số kiểu có tên theo quy tắc cận của Java; không dùng wildcard như một biến kiểu có thể tham chiếu lại.

### 7.4. Cho rằng nhiều wildcard tự tạo quan hệ nghiệp vụ

`Map<? extends CharSequence, ? extends Number>` cho biết phạm vi kiểu khóa và giá trị. Nó không chứng minh khóa là tên người, giá trị là điểm hợp lệ hay hai map nói về cùng một tập khóa.

Kiểu tổng quát bảo vệ quan hệ kiểu; ràng buộc nghiệp vụ vẫn cần mô hình dữ liệu hoặc kiểm tra riêng.

### 7.5. Nhầm quyền kiểu với khả năng sửa dữ liệu

`Map<? super String, ? super Integer>` cho phép truyền `String` và `Integer` vào `put` theo kiểu tĩnh. Đối tượng map vẫn có thể không hỗ trợ sửa đổi. Ví dụ map tạo bằng `Map.of` không nhận thao tác thêm hoặc cập nhật.

Tương tự, `extends` không phải một cơ chế khóa dữ liệu. Một tham chiếu khác có thể thay đổi cùng đối tượng. Hợp đồng về tính bất biến, `null`, thứ tự và truy cập đồng thời cần được xác định riêng.

## 8. Cách thiết kế chữ ký từng bước

Với một thuật toán có nhiều kiểu:

1. Đặt tên cho những kiểu cần liên hệ giữa nguồn, đích, hàm xử lý và kết quả.
2. Với từng vị trí, ghi rõ thuật toán đọc hay ghi giá trị mang kiểu đó.
3. Chọn `extends` cho nguồn cung cấp, `super` cho nơi nhận; giữ đối số kiểu chính xác khi cần ràng buộc chính xác.
4. Kiểm tra riêng từng tầng nếu có kiểu lồng nhau.
5. Thử một lời gọi hợp lệ với kiểu rộng hơn và một lời gọi không hợp lệ ở từng vị trí.
6. Giữ kiểu trả về rõ ràng khi có thể; không đẩy wildcard ra ngoài chỉ để chữ ký trông tổng quát hơn.

Thử giải thích bằng lời chữ ký sau:

```java
<K, V, R> List<R> mapEntries(
        Map<? extends K, ? extends V> source,
        BiFunction<? super K, ? super V, ? extends R> mapper)
```

Một cách đọc đầy đủ: “Đọc các khóa dùng được như `K` và giá trị dùng được như `V`; đưa từng cặp cho một hàm nhận được `K` và `V`; thu các kết quả dùng được như `R` vào một danh sách `R`.”

## Tài liệu đối chiếu

- [Java Map API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): đối chiếu các chữ ký `putAll`, `forEach` và `compute` để thấy wildcard được chọn riêng cho từng vai trò.
- [Java BiFunction API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiFunction.html): hai tham số đầu vào và một tham số kết quả.
- [JLS §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10): cơ chế xử lý các kiểu chưa biết khi dùng wildcard.
