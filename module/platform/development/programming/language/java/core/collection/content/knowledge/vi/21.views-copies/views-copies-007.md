# Map.Entry còn gắn nguồn so với entry độc lập

## 1. Cùng kiểu Entry nhưng khác quan hệ sở hữu

`Map.Entry<K,V>` biểu diễn một cặp khóa–giá trị. Nhìn chữ ký ấy, bạn biết có thể hỏi `getKey()` và `getValue()`, còn `setValue(v)` là một thao tác tùy chọn.

Nhưng kiểu giao diện chưa nói cặp này **còn kết nối với một map** hay **chỉ là dữ liệu độc lập**. Đây là khác biệt quyết định khi muốn cập nhật map, giữ kết quả để dùng sau, trả dữ liệu qua API hoặc tạo ảnh chụp.

Hãy hình dung hai tình huống:

~~~text
Tình huống A:
entry đang được iterator của map trả về
        |
        +--- setValue được nguồn hỗ trợ ---> giá trị trong map đổi

Tình huống B:
entry được tạo bằng new SimpleEntry(...)
        |
        +--- setValue ---> chỉ cặp độc lập đổi
~~~

Tài liệu `Map.Entry` phân biệt rõ entry có thể sửa hoặc không sửa được, có thể độc lập hoặc đại diện cho entry trong view của map. Đối với entry iterator, kết nối với nguồn có phạm vi hợp lệ gắn với quá trình duyệt. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Bài này giúp bạn trả lời ba câu hỏi riêng: entry lấy từ đâu, sửa nó có ghi vào map nào không, và dữ liệu bên trong có còn được chia sẻ không. Chương trình đầy đủ dùng **Java 17 trở lên**, bao gồm `Map.Entry.copyOf` có từ Java 17.

## 2. Ba trục không được gộp làm một

Một entry cần được đánh giá theo ba trục:

| Trục | Hai khả năng thường gặp | Câu hỏi thực tế |
| --- | --- | --- |
| Kết nối nguồn | Gắn với map hoặc độc lập | Sửa entry có thể tác động map không? |
| Thay giá trị của cặp | `setValue` được hỗ trợ hoặc bị từ chối | Có thể đổi tham chiếu value của entry không? |
| Trạng thái khóa/giá trị | Đối tượng bất biến hoặc sửa được | Dù cặp không đổi tham chiếu, dữ liệu bên trong có đổi không? |

Một entry độc lập có thể **sửa được**, như `SimpleEntry`. Một entry không sửa được có thể chứa **giá trị sửa được**, như một `ArrayList`. Một entry đang được duyệt qua map chỉ đọc không phải lối mở để cập nhật nguồn.

Vì thế, các từ “copy”, “immutable” hoặc “view” cần gắn với chính xác tầng dữ liệu đang nói đến. Đừng dùng một từ để suy hết mọi quyền và vòng đời.

## 3. Entry lấy từ iterator của entrySet

### 3.1. Cập nhật giá trị trong phạm vi duyệt được hỗ trợ

Ví dụ với một `LinkedHashMap` sửa được:

~~~java
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    if (entry.getKey().equals("sku-A")) {
        Integer oldValue = entry.setValue(11);
    }
}
~~~

Đây là đoạn minh họa đặt trong phương thức có import và nguồn `stock` phù hợp.

Lời gọi `setValue(11)` thay giá trị của ánh xạ hiện tại trong map, nếu nguồn hỗ trợ thao tác ấy. Nó trả giá trị cũ, không trả cờ `boolean` và không trả entry mới.

Khóa không bị đổi bởi `setValue`. Nếu nguồn trước có `sku-A=10`, sau cập nhật có `sku-A=11`. Số ánh xạ vẫn giữ nguyên.

`Map.entrySet` cho phép thao tác `setValue` trên entry do iterator trả về trong phạm vi mà nguồn hỗ trợ, bên cạnh đường xóa qua iterator. [Java 17: Map.entrySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()).

### 3.2. Gán lại biến entry không phải cập nhật nguồn

Đoạn sau chỉ thay một biến cục bộ:

~~~java
entry = new AbstractMap.SimpleEntry<>(entry.getKey(), 11);
~~~

Nó không gọi một phương thức cập nhật map. Biến `entry` trỏ đến cặp mới, nhưng ánh xạ gốc không tự nhận giá trị ấy.

Tương tự, gán `value = 11` cho biến value đọc được trước đó không biến biến ấy thành một ô tham chiếu của map.

Cập nhật nguồn phải đi qua một API có hợp đồng ghi xuyên, như `setValue` hợp lệ trên entry đang kết nối hoặc phương thức cập nhật của map.

### 3.3. Vòng đời: không giữ entry iterator làm tay nắm lâu dài

Bảo đảm kết nối của entry iterator không phải lời hứa “entry này sẽ theo khóa ấy mãi mãi”. Hợp đồng Java 17 giới hạn việc dùng entry vào quá trình duyệt; nếu map bị sửa sau khi entry được iterator trả về, ngoài việc sửa qua chính `setValue` theo hợp đồng, bạn không được tiếp tục dựa vào hành vi của entry cũ như một API ổn định.

Đặc biệt, không lấy một entry, kết thúc vòng lặp, xóa khóa khỏi map, rồi gọi `setValue` trên entry đó và đoán rằng nó sẽ thêm khóa trở lại hoặc chắc chắn ném một ngoại lệ cụ thể.

Một lần thử trên một cách triển khai có thể còn thấy dữ liệu cũ hay một nút nội bộ. Điều đó không nâng thành bảo đảm của giao diện. Nếu cần dùng về sau, hãy tạo cặp độc lập khi entry còn đang được đọc hợp lệ.

### 3.4. setValue không thay cho xóa

Nếu nguồn cho phép `null`, `entry.setValue(null)` gán giá trị `null`; khóa vẫn tồn tại. Nếu nguồn cấm `null`, thao tác có thể bị từ chối theo ràng buộc của nó.

Muốn xóa ánh xạ hiện tại trong lần duyệt, dùng `Iterator.remove` theo quy tắc iterator hoặc chọn một phép lọc thích hợp. Muốn thay khóa, phải thiết kế một thao tác khác; entry không có `setKey`.

## 4. Các cách tạo entry độc lập

### 4.1. SimpleEntry: cặp độc lập có thể thay value

~~~java
Map.Entry<String, Integer> local =
        new AbstractMap.SimpleEntry<>("sku-A", 50);
Integer oldValue = local.setValue(60);
~~~

Cặp `local` trở thành `sku-A=60`; `oldValue` là `50`. Không map nào tự được cập nhật chỉ vì trong chương trình có một map cũng chứa khóa `sku-A`.

`SimpleEntry` giữ khóa và giá trị riêng, hỗ trợ `setValue` và không thuộc entry-set view của map nào. Nó có constructor nhận hai thành phần hoặc nhận một entry để sao chép cặp. [Java 17: AbstractMap.SimpleEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).

Nếu muốn đưa giá trị cặp này vào map, phải thao tác rõ:

~~~java
stock.put(local.getKey(), local.getValue());
~~~

Sau đó sửa `local` lần nữa không tự sửa map. Lệnh `put` nhận khóa/giá trị, không thiết lập một quan hệ liên kết sống với đối tượng entry độc lập này.

### 4.2. SimpleImmutableEntry: độc lập, không hỗ trợ thay value của cặp

~~~java
Map.Entry<String, Integer> saved =
        new AbstractMap.SimpleImmutableEntry<>("sku-A", 50);
~~~

Cặp độc lập này không cho đổi value qua `setValue`; thao tác ấy ném `UnsupportedOperationException` trên lớp cụ thể này. Các tham chiếu khóa/giá trị được giữ, nhưng đối tượng mà chúng trỏ đến có thể vẫn sửa được.

Tài liệu lớp nói rõ tính không sửa được của cặp không đồng nghĩa khóa và giá trị bất biến sâu. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Nếu dùng constructor nhận entry, bạn sao chép các thành phần của entry tại thời điểm đọc hợp lệ. Bạn không tiếp tục giữ kết nối entry-set của đối tượng nguồn.

### 4.3. Map.entry(k, v): factory gọn cho cặp không sửa được

~~~java
Map.Entry<String, Integer> pair = Map.entry("sku-A", 50);
~~~

Cặp được tạo độc lập, không cho `setValue` và không nhận khóa hoặc giá trị `null`. Chỉ tạo entry không tự chèn nó vào một map nào.

Các entry từ factory này là đối tượng theo giá trị; không dựa vào đồng nhất tham chiếu `==` hay dùng chúng làm khóa đồng bộ. Chúng không được bảo đảm là những đối tượng cấp phát mới khác nhau mỗi lần gọi. [Java 17: Map.entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entry(K,V)).

Nếu cần lưu trữ lâu dài hoặc truyền qua tầng ứng dụng, một kiểu dữ liệu miền rõ tên có thể diễn đạt ý nghĩa tốt hơn một cặp chung. Nhưng `Map.entry` là lựa chọn hữu ích khi bạn thực sự cần hợp đồng `Map.Entry` và miền dữ liệu không có `null`.

### 4.4. Map.Entry.copyOf(existing): tách một cặp khỏi nguồn từ Java 17

~~~java
Map.Entry<String, Integer> snapshot = Map.Entry.copyOf(entry);
~~~

Kết quả không gắn với map nào, không hỗ trợ `setValue` và có cùng đặc tính thành phần như `Map.entry`. Đối số entry, khóa và value đều không được `null`.

Đừng kiểm chứng việc “đã tách” bằng cách bắt buộc `snapshot != entry`. Nếu đầu vào vốn đã là entry độc lập thích hợp, factory có thể tái sử dụng đối tượng. Điều cần kiểm chứng là hợp đồng dữ liệu và không có đường cập nhật map nguồn qua cặp ấy, không phải một điều kiện định danh không được hứa.

### 4.5. Bảng chọn nhanh

| Cách nhận/tạo | Gắn nguồn? | Thay value qua setValue? | Thành phần null |
| --- | --- | --- | --- |
| Entry iterator của nguồn sửa được, trong lúc duyệt | Có kết nối theo hợp đồng | Tùy nguồn; ví dụ LinkedHashMap hỗ trợ | Theo nguồn |
| `new SimpleEntry(k, v)` | Không | Có trên lớp này | Có thể giữ `null` |
| `new SimpleImmutableEntry(k, v)` | Không | Không trên lớp này | Có thể giữ `null` |
| `Map.entry(k, v)` | Không | Không | Từ chối |
| `Map.Entry.copyOf(e)` | Không | Không | Từ chối |
| Entry từ view của map không sửa được | Không phải quyền cập nhật nguồn | Bị chặn qua đường này | Theo nguồn/lớp bọc |

“Có thể giữ `null`” ở hai lớp entry độc lập nói về chính cặp. Khi đưa các thành phần của nó vào một map cấm `null`, map ấy vẫn có quyền từ chối.

## 5. Tạo ảnh chụp entry đúng tầng

### 5.1. Sao chép collection không tự sao chép từng entry

Đoạn sau tạo một list mới:

~~~java
List<Map.Entry<String, Integer>> saved =
        new ArrayList<>(stock.entrySet());
~~~

Nhưng phần tử của list vẫn là những đối tượng entry lấy từ nguồn. Không thể chỉ nhìn `new ArrayList` rồi kết luận các cặp đã được tách độc lập.

Ngay cả `List.copyOf(stock.entrySet())` chỉ giải quyết hợp đồng của list bên ngoài, không tự biến mỗi phần tử thành một `Map.Entry.copyOf`.

### 5.2. Sao chép từng cặp trong lúc duyệt hợp lệ

Với miền không có khóa/giá trị `null`:

~~~java
List<Map.Entry<String, Integer>> snapshots = new ArrayList<>();
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    snapshots.add(Map.Entry.copyOf(entry));
}
~~~

Mỗi entry được đọc và sao chép trong vòng lặp. Sau đó có thể giữ các cặp độc lập dù map tiếp tục thêm/xóa/thay ánh xạ.

Nếu cần các cặp độc lập nhưng có thể sửa cục bộ, tạo `new SimpleEntry<>(entry)`. Nếu có `null` và muốn cặp không cho thay value, có thể tạo `new SimpleImmutableEntry<>(entry)` theo chính sách dữ liệu.

Danh sách bên ngoài ở đây là `ArrayList` nên vẫn thêm/xóa phần tử danh sách được. Việc cặp không cho `setValue` không tự làm list không sửa được. Nếu muốn cả hai tầng bị giới hạn, cần lựa chọn thêm cho tầng list.

### 5.3. Dạng stream cũng cần bước biến đổi entry

Trong Java 17, có thể viết:

~~~java
List<Map.Entry<String, Integer>> snapshots =
        stock.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
~~~

Bước quan trọng là `map(Map.Entry::copyOf)`. Chỉ `entrySet().stream().toList()` không tự tách từng cặp khỏi nguồn.

`Stream.toList` ở cách dùng này cho list không sửa được, còn quyền của entry do bước tạo entry quyết định. Tài liệu `Map.Entry` giới thiệu chính cách sao chép từng cặp để có dữ liệu không gắn nguồn; các quy tắc `null` vẫn cần được thỏa mãn.

## 6. Entry không sửa được vẫn có thể chia sẻ trạng thái sửa được

Ví dụ:

~~~java
List<String> tags = new ArrayList<>(List.of("a"));
Map.Entry<String, List<String>> pair = Map.entry("tags", tags);
Map.Entry<String, List<String>> snapshot = Map.Entry.copyOf(pair);
tags.add("b");
~~~

`snapshot.getValue()` nhìn thấy `[a, b]` vì cặp giữ tham chiếu đến cùng danh sách `tags`. Bạn không đổi tham chiếu value của entry; bạn sửa chính đối tượng value.

Mô hình:

~~~text
pair.value --------+
                   +----> List tags đang sửa được
snapshot.value ----+
~~~

Đây là **sao chép nông**. Tính độc lập với map nguồn nói về quan hệ của cặp với ánh xạ, không tự nói mọi đối tượng phía sau tham chiếu đã được nhân bản.

### 6.1. Khi dữ liệu con là danh sách chuỗi

Có thể tạo một giá trị danh sách riêng không sửa được:

~~~java
Map.Entry<String, List<String>> safe =
        Map.entry("tags", List.copyOf(tags));
~~~

Sau đó thêm phần tử vào danh sách `tags` gốc không làm list của `safe` tăng phần tử. Với các phần tử chuỗi bất biến, cách này tạo mức độc lập cần thiết cho ví dụ.

`List.copyOf` không nhận `null` và không tự sao chép sâu từng đối tượng phần tử. Nếu phần tử danh sách là đối tượng có thể sửa, cần tiếp tục xác định độ sâu phù hợp. [Java 17: List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Đừng gọi mọi cặp chứa một collection không sửa được là “bất biến sâu” khi các phần tử bên trong còn thay đổi.

### 6.2. Khóa cũng có thể là đối tượng thay đổi

Không có `setKey` không có nghĩa đối tượng khóa bất biến. Một entry có thể giữ tham chiếu đến một khóa tự định nghĩa có các trường sửa được.

Nếu chính đối tượng ấy đang dùng làm khóa trong map hoặc thành viên trong set băm, thay các trường ảnh hưởng phép bằng/băm có thể phá giả định tra cứu. Chọn các kiểu khóa ổn định theo mục đích sử dụng; entry độc lập không sửa được không tự làm khóa ổn định.

## 7. Entry từ API điều hướng thường là ảnh chụp

`NavigableMap` có `firstEntry`, `lastEntry`, `floorEntry`, `ceilingEntry` và các phương thức lấy bỏ như `pollFirstEntry`. Chúng trả cặp phục vụ việc tìm một ánh xạ ở thời điểm gọi, khác việc bạn đang duyệt entry-set.

Tài liệu `NavigableMap` mô tả các entry điều hướng theo hướng ảnh chụp và nói chúng nhìn chung không hỗ trợ `setValue`. Chương trình dùng `TreeMap.firstEntry` để kiểm chứng cụ thể. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html).

Ví dụ nguồn `{1=one, 2=two}`:

~~~text
before = firstEntry()             before là 1=one
nguồn put(1, ONE)                 nguồn là {1=ONE, 2=two}
before                           vẫn mô tả 1=one
before.setValue(X)                bị từ chối ở entry ảnh chụp này
~~~

Muốn cập nhật map, dùng API map phù hợp. Muốn tìm ánh xạ đầu rồi cập nhật trong môi trường nhiều luồng như một thao tác thống nhất, cần một hợp đồng đồng thời riêng; việc nhận ảnh chụp không tự giữ chỗ cho khóa hay ánh xạ.

### 7.1. Poll trả entry của ánh xạ đã bị lấy bỏ

`pollFirstEntry` vừa xóa ánh xạ đầu vừa trả thông tin về ánh xạ ấy, hoặc trả `null` nếu không có. Entry kết quả không phải một cách ngầm để đưa ánh xạ trở lại nguồn bằng `setValue`.

Nếu muốn khôi phục hoặc đưa dữ liệu vào map, phải gọi thao tác map rõ ràng, có xét xem khóa hiện đã được một thao tác khác thêm lại hay chưa.

### 7.2. Liên hệ với SequencedMap từ Java 21

Từ Java 21, `SequencedMap` quy định `firstEntry`, `lastEntry`, `pollFirstEntry` và `pollLastEntry` trả ảnh chụp không hỗ trợ sửa nguồn bằng `setValue`.

Giao diện này cũng nhấn mạnh rằng entry nhận bằng một cách khác như `sequencedEntrySet().getFirst()` không có cùng bảo đảm chung về kết nối hay khả năng sửa. Không suy chỉ từ kiểu `Map.Entry` và chữ “first” rằng hai cách lấy có hợp đồng giống nhau. [Java 21: SequencedMap, vòng đời entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

Đoạn liên hệ này nói về API Java 21. Chương trình chính không dùng `SequencedMap` để vẫn biên dịch với mục tiêu Java 17.

## 8. Lớp bọc chỉ đọc và việc trả entry qua API

`Collections.unmodifiableMap(source)` chặn sửa map qua các phương thức map và collection view của lớp bọc, bao gồm đường `setValue` qua entry do nó cung cấp.

Đó vẫn là view nguồn, không phải một bản sao trạng thái cố định. Thay map gốc qua một tham chiếu khác có thể được nhìn thấy qua lớp bọc. [Java 17: Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

Cần tách hai mục tiêu:

- **không trao quyền cập nhật map:** dùng lớp bọc đúng hoặc trả cặp độc lập;
- **giữ dữ liệu tại một thời điểm:** sao chép theo mức cần thiết và điều kiện đọc nhất quán.

Chỉ bọc collection bên ngoài, chẳng hạn `Collections.unmodifiableSet(source.entrySet())`, không tự làm các đối tượng entry bên trong mất quyền `setValue`. Bảo vệ một tầng không tự bảo vệ tầng phần tử.

Nếu một hàm tìm “mục tốt nhất” rồi trả entry để xử lý về sau, cặp độc lập thường biểu đạt dữ liệu kết quả rõ hơn entry iterator bị kéo dài vòng đời. Nếu hàm thật sự cần trao một lệnh cập nhật có kiểm soát, một API cập nhật theo khóa và điều kiện nghiệp vụ thường rõ hơn trả tay nắm entry.

## 9. equals và hashCode không cho biết entry còn gắn nguồn hay không

Entry chuẩn so sánh cả khóa lẫn giá trị. Một `SimpleEntry("item", 1)` và `Map.entry("item", 1)` có thể `equals` nhau dù quyền sửa và nguồn gốc khác nhau.

Sau `simple.setValue(2)`, cặp ấy không còn bằng cặp `item=1`. Vì phép bằng và mã băm phụ thuộc các thành phần, thay value có thể thay `hashCode` của entry.

Do đó:

- `equals` nhau không chứng minh cùng quyền cập nhật;
- `equals` nhau không chứng minh có chung nguồn;
- `==` không phải kiểm chứng đúng cho các factory theo giá trị;
- không nên đặt một entry có nội dung thay đổi làm khóa băm hoặc thành viên set băm rồi sửa thành phần ảnh hưởng phép bằng/băm khi nó đang nằm trong cấu trúc ấy.

`Set` cảnh báo về phần tử có trạng thái thay đổi theo cách ảnh hưởng phép bằng trong khi vẫn thuộc set. [Java 17: Set, phần tử có thể thay đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

Nếu cần định danh lâu dài cho một ánh xạ, dùng khóa có hợp đồng phù hợp; nếu cần ghi lại một cặp, dùng cặp dữ liệu theo giá trị và ổn định ở mức mà việc ghi nhận yêu cầu.

## 10. Chương trình đầy đủ

Lưu toàn bộ mã dưới vào **`EntryOwnershipDemo.java`**. Chương trình không giữ hoặc sử dụng entry iterator sau khi kết thúc quá trình duyệt. Các cặp cần giữ đều được tạo độc lập ngay trong vòng lặp.

Nguồn chính là `LinkedHashMap` mặc định theo thứ tự chèn để stdout có thể dự đoán. Nó không làm mọi map khác có cùng thứ tự. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class EntryOwnershipDemo {
    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("sku-A", 10);
        stock.put("sku-B", 20);
        List<Map.Entry<String, Integer>> snapshots = new ArrayList<>();
        List<AbstractMap.SimpleEntry<String, Integer>> localCopies = new ArrayList<>();

        for (Map.Entry<String, Integer> entry : stock.entrySet()) {
            if (entry.getKey().equals("sku-A")) {
                int previous = entry.setValue(11);
                System.out.println("connected setValue previous: " + previous);
            }
            snapshots.add(Map.Entry.copyOf(entry));
            localCopies.add(new AbstractMap.SimpleEntry<>(entry));
        }
        System.out.println("source after iteration: " + stock);
        System.out.println("captured snapshots: " + snapshots);

        stock.put("sku-A", 15);
        stock.remove("sku-B");
        stock.put("sku-C", 30);
        System.out.println("source changed later: " + stock);
        System.out.println("snapshots stay: " + snapshots);
        System.out.println("mutable copies stay: " + localCopies);

        AbstractMap.SimpleEntry<String, Integer> local = localCopies.get(0);
        int previous = local.setValue(99);
        System.out.println("local setValue previous: " + previous + ", local=" + local);
        System.out.println("source unaffected by local edit: " + stock);
        stock.put(local.getKey(), local.getValue());
        local.setValue(100);
        System.out.println("explicit put then local edit: local=" + local + ", source=" + stock);

        Map.Entry<String, Integer> frozen = Map.Entry.copyOf(local);
        local.setValue(101);
        System.out.println("copyOf detached pair: " + frozen + ", local now=" + local);
        System.out.println("copyOf setValue: " + failure(() -> frozen.setValue(500)));

        Map.Entry<String, Integer> literal = Map.entry("fixed", 7);
        Map.Entry<String, Integer> immutable =
                new AbstractMap.SimpleImmutableEntry<>("fixed", 7);
        System.out.println("Map.entry setValue: " + failure(() -> literal.setValue(8)));
        System.out.println("SimpleImmutableEntry setValue: "
                + failure(() -> immutable.setValue(8)));
        System.out.println("independent pair auto-inserted: " + stock.containsKey("fixed"));

        AbstractMap.SimpleEntry<String, Integer> nullLocal =
                new AbstractMap.SimpleEntry<>(null, null);
        Map.Entry<String, Integer> nullFrozen =
                new AbstractMap.SimpleImmutableEntry<>(null, null);
        System.out.println("independent null pair: " + nullFrozen);
        System.out.println("null local old value: " + nullLocal.setValue(10)
                + ", now=" + nullLocal);
        System.out.println("Map.entry null value: "
                + failure(() -> Map.entry("N", null)));
        System.out.println("copyOf null components: "
                + failure(() -> Map.Entry.copyOf(nullFrozen)));

        NavigableMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(1, "one");
        sorted.put(2, "two");
        Map.Entry<Integer, String> first = sorted.firstEntry();
        sorted.put(1, "ONE");
        System.out.println("navigation snapshot: " + first + ", current=" + sorted);
        System.out.println("navigation setValue: " + failure(() -> first.setValue("X")));
        Map.Entry<Integer, String> removed = sorted.pollFirstEntry();
        System.out.println("polled snapshot: " + removed + ", source=" + sorted);

        Map<String, Integer> readOnly = Collections.unmodifiableMap(stock);
        System.out.println("read-only iterator entry: " + failure(() -> {
            for (Map.Entry<String, Integer> entry : readOnly.entrySet()) {
                entry.setValue(0);
            }
        }));

        List<String> tags = new ArrayList<>(List.of("a"));
        Map.Entry<String, List<String>> pair = Map.entry("tags", tags);
        Map.Entry<String, List<String>> shallow = Map.Entry.copyOf(pair);
        tags.add("b");
        System.out.println("unmodifiable pair shares payload: " + shallow);
        Map.Entry<String, List<String>> protectedPayload =
                Map.entry("tags", List.copyOf(tags));
        tags.add("c");
        System.out.println("shallow after another edit: " + shallow);
        System.out.println("copied string-list payload: " + protectedPayload);
        System.out.println("protected payload add: "
                + failure(() -> protectedPayload.getValue().add("d")));

        AbstractMap.SimpleEntry<String, Integer> left =
                new AbstractMap.SimpleEntry<>("item", 1);
        Map.Entry<String, Integer> right = Map.entry("item", 1);
        System.out.println("equal across entry implementations: " + left.equals(right));
        left.setValue(2);
        System.out.println("equal after value replacement: " + left.equals(right));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 EntryOwnershipDemo.java
java EntryOwnershipDemo
~~~

Dùng JDK 17 trở lên để biên dịch ở mức release 17 và runtime Java 17 trở lên để chạy. Ví dụ đã được biên dịch với mức release 17 và chạy thành công bằng OpenJDK 24.0.2.

Stdout chính xác:

~~~text
connected setValue previous: 10
source after iteration: {sku-A=11, sku-B=20}
captured snapshots: [sku-A=11, sku-B=20]
source changed later: {sku-A=15, sku-C=30}
snapshots stay: [sku-A=11, sku-B=20]
mutable copies stay: [sku-A=11, sku-B=20]
local setValue previous: 11, local=sku-A=99
source unaffected by local edit: {sku-A=15, sku-C=30}
explicit put then local edit: local=sku-A=100, source={sku-A=99, sku-C=30}
copyOf detached pair: sku-A=100, local now=sku-A=101
copyOf setValue: UnsupportedOperationException
Map.entry setValue: UnsupportedOperationException
SimpleImmutableEntry setValue: UnsupportedOperationException
independent pair auto-inserted: false
independent null pair: null=null
null local old value: null, now=null=10
Map.entry null value: NullPointerException
copyOf null components: NullPointerException
navigation snapshot: 1=one, current={1=ONE, 2=two}
navigation setValue: UnsupportedOperationException
polled snapshot: 1=ONE, source={2=two}
read-only iterator entry: UnsupportedOperationException
unmodifiable pair shares payload: tags=[a, b]
shallow after another edit: tags=[a, b, c]
copied string-list payload: tags=[a, b]
protected payload add: UnsupportedOperationException
equal across entry implementations: true
equal after value replacement: false
~~~

### 10.1. Ghi xuyên trong vòng lặp, sao chép trước khi rời vòng lặp

Entry `sku-A` đang được duyệt cập nhật nguồn từ `10` lên `11` và trả giá trị cũ `10`. Cả ảnh chụp không sửa được lẫn bản cặp sửa được đều được tạo sau bước cập nhật ấy, nên lưu `sku-A=11`.

Sau vòng lặp, nguồn đổi thành `{sku-A=15, sku-C=30}`. Các cặp đã sao chép vẫn giữ `sku-A=11` và `sku-B=20`. Việc `sku-B` bị xóa khỏi nguồn không khiến các cặp độc lập mất dữ liệu.

### 10.2. Sửa cặp cục bộ và áp dữ liệu vào map là hai hành động

`local.setValue(99)` chỉ đổi bản cặp cục bộ. Lệnh `stock.put(local.getKey(), local.getValue())` sau đó mới cập nhật map thành `sku-A=99`.

Tiếp tục đổi `local` thành `100` không làm map nhận `100`. `copyOf(local)` lấy cặp `sku-A=100` độc lập; đổi `local` thành `101` cũng không làm ảnh chụp ấy đổi.

### 10.3. null, điều hướng và lớp bọc

Hai lớp entry độc lập có thể giữ thành phần `null`, trong khi hai factory `Map.entry` và `Map.Entry.copyOf` được kiểm tra trong ví dụ từ chối thành phần `null`.

Entry đầu của `TreeMap` giữ giá trị trước khi map được cập nhật, rồi từ chối `setValue`. Entry từ `pollFirstEntry` mô tả ánh xạ đã bị lấy bỏ. Entry qua map chỉ đọc cũng từ chối cập nhật.

### 10.4. Bất biến cặp khác bất biến dữ liệu con

Cặp `tags` không đổi tham chiếu nhưng danh sách giá trị được chia sẻ vẫn tăng từ `[a]` lên `[a, b]` rồi `[a, b, c]`.

Bản giữ `List.copyOf(tags)` được tạo trước lần thêm `c`, nên còn `[a, b]` và không cho thêm `d`. Điều này đủ cho ví dụ danh sách chuỗi; không tự là giải pháp sao chép sâu cho mọi kiểu giá trị.

## 11. Lưu và truyền entry trong mã thực tế

### 11.1. Trả dữ liệu cho xử lý về sau

Khi nhận một entry từ nguồn, hãy xác định bên nhận còn dùng trong cùng lần duyệt hay sau đó. Nếu vượt phạm vi duyệt, sao chép cặp hoặc chuyển sang kiểu dữ liệu miền phù hợp ngay lúc đọc hợp lệ.

Đối với lịch sử hoặc sự kiện, còn cần xác định giá trị con có thể đổi không. Một sự kiện “đã ghi giá trị tại thời điểm T” không đạt yêu cầu nếu nó chỉ giữ tham chiếu đến một danh sách còn được sửa về sau.

### 11.2. Ảnh chụp một cặp khác ảnh chụp nguyên tử toàn map

Sao chép từng entry bảo đảm cặp mới không còn là đường ghi xuyên vào ánh xạ nguồn. Nó không tự bảo đảm tất cả cặp của một list ảnh chụp được đọc tại cùng một thời điểm nếu nguồn đang thay đổi đồng thời.

Ngay cả nguồn đồng thời như `ConcurrentHashMap` cũng có chính sách quan sát tổng hợp riêng; iterator có thể phản ánh các trạng thái từ thời điểm khác nhau trong quá trình duyệt. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Nếu yêu cầu là một báo cáo nhất quán trên nhiều ánh xạ, phải có cơ chế đọc/công bố trạng thái phù hợp ở tầng sở hữu. Đừng dùng chữ “snapshot” của từng cặp để ngầm hứa một giao dịch của toàn bộ dữ liệu.

### 11.3. Không dùng ảnh chụp làm giấy phép cập nhật vô điều kiện

Giả sử bạn sao chép `product=10`, rồi một tác vụ khác đổi nguồn thành `product=12`. Sau đó lấy value từ ảnh chụp cũ để `put` trở lại có thể ghi đè dữ liệu mới.

Entry độc lập giúp kiểm soát vòng đời dữ liệu, nhưng không giải quyết xung đột cập nhật. Nếu yêu cầu phải cập nhật trên nền một giá trị kỳ vọng, hãy chọn API có điều kiện và cơ chế đồng thời phù hợp với nguồn.

### 11.4. Kiểm thử bằng hành vi được cam kết

Một kiểm thử tốt có thể xác nhận:

- `setValue` hợp lệ trong vòng lặp trên nguồn hỗ trợ cập nhật đúng map;
- cặp độc lập sửa cục bộ không tự ghi nguồn;
- ảnh chụp giữ cặp sau các cập nhật nguồn về sau;
- thao tác không được hỗ trợ ném đúng ngoại lệ theo lớp/factory đã chọn;
- dữ liệu con được chia sẻ hoặc sao chép đúng mức đã thiết kế.

Không viết kiểm thử dựa vào việc sử dụng một entry iterator đã hết phạm vi rồi đoán nó “nên” còn liên kết hay “nên” bị tách. Tránh biến hành vi ngoài hợp đồng thành yêu cầu phải duy trì.

## 12. Lỗi thường gặp

| Hiểu nhầm | Điều bị bỏ sót | Cách xử lý |
| --- | --- | --- |
| Mọi Map.Entry là một ô sống của map | Entry có thể độc lập hoặc là ảnh chụp | Xác định nơi tạo/lấy |
| Mọi setValue đều sửa nguồn | SimpleEntry chỉ sửa cặp riêng | Dùng API cập nhật đúng ý định |
| Entry iterator giữ được mãi | Kết nối có phạm vi duyệt | Sao chép khi cần giữ |
| new ArrayList(entrySet) tách mọi cặp | Chỉ có collection ngoài mới | Sao chép từng entry |
| Map.entry tự chèn dữ liệu | Factory chỉ tạo cặp | Gọi map.put nếu muốn thêm |
| copyOf phải trả đối tượng khác == | Factory có thể tái sử dụng | Kiểm chứng hợp đồng theo giá trị |
| Tên Immutable làm dữ liệu con bất biến | Tham chiếu có thể trỏ đối tượng sửa được | Sao chép/bọc theo từng tầng |
| Entry điều hướng luôn cho ghi nguồn | Nhiều API trả ảnh chụp không sửa được | Dùng API map phù hợp |
| Cặp equals nhau có cùng quyền sửa | Phép bằng chỉ xét khóa/value | Tách quyền thao tác khỏi dữ liệu |
| Sao chép cặp giải quyết mọi tranh chấp | Vẫn có dữ liệu cũ và thay đổi đồng thời | Thiết kế nhất quán và điều kiện cập nhật |

## 13. Thực hành có đáp án

### Bài 1 — Nguồn gốc quyết định tác dụng

Bạn có entry `e` do iterator của một `LinkedHashMap` sửa được trả về trong vòng lặp và entry `p = new SimpleEntry<>(e)`. Gọi `e.setValue(8)` rồi `p.setValue(9)` trong điều kiện hợp lệ. Lệnh nào cập nhật nguồn?

**Đáp án:** `e.setValue(8)` cập nhật ánh xạ nguồn nếu được hỗ trợ. `p` là cặp độc lập; `p.setValue(9)` chỉ đổi cặp ấy. Thời điểm tạo `p` quyết định value nó ghi nhận ban đầu, nhưng không tạo kết nối sống về sau.

### Bài 2 — Giữ entry để dùng sau

Một hàm duyệt map rồi trả thẳng một entry iterator tìm được để bên gọi sửa vào ngày hôm sau. Có thể dựa vào hợp đồng chung không?

**Đáp án:** không. Entry iterator không phải tay nắm cập nhật lâu dài được giao diện bảo đảm. Nếu cần dữ liệu để dùng sau, tạo cặp độc lập lúc đang đọc hợp lệ. Nếu cần cập nhật, thiết kế API theo khóa/điều kiện và chính sách sở hữu phù hợp.

### Bài 3 — List mới có đủ chưa?

`new ArrayList<>(map.entrySet())` có bảo đảm từng entry là ảnh chụp độc lập không? Cần thêm bước gì khi dữ liệu không có null?

**Đáp án:** chưa. Nó chỉ tạo list ngoài. Có thể sao chép từng entry bằng `Map.Entry.copyOf` trong lúc duyệt, hoặc dùng phép biến đổi tương ứng trong stream. Nếu cần giữ `null`, chọn một cách tạo cặp phù hợp như `SimpleImmutableEntry` theo chính sách dữ liệu.

### Bài 4 — Factory và null

So sánh `new SimpleImmutableEntry<>("K", null)` với `Map.entry("K", null)` và `Map.Entry.copyOf` của cặp đầu.

**Đáp án:** lớp entry cụ thể đầu có thể giữ giá trị `null` và không hỗ trợ `setValue`. `Map.entry` từ chối thành phần `null`; `copyOf` cũng từ chối cặp có khóa/value `null`. Việc nguồn map cho `null` không tự làm factory khác nhận `null`.

### Bài 5 — Bất biến cặp nhưng không bất biến List

Cặp được tạo bằng `Map.entry("items", mutableList)` và sao chép bằng `copyOf`. Sau đó thêm phần tử vào `mutableList`. Ảnh chụp có thể nhìn thấy không?

**Đáp án:** có vì các cặp giữ tham chiếu đến cùng list. Không đổi tham chiếu value không đồng nghĩa list không đổi trạng thái. Với danh sách chuỗi, có thể sao chép list thành `List.copyOf` theo yêu cầu; với phần tử sửa được, cần xác định tiếp độ sâu.

### Bài 6 — Entry của firstEntry

`TreeMap` đang có `1=one`. Lấy `before = firstEntry()` rồi cập nhật map thành `1=ONE`. Có dùng `before.setValue` để cập nhật tiếp được trong ví dụ không?

**Đáp án:** không; entry điều hướng của nguồn này là ảnh chụp không hỗ trợ `setValue`. Nó ghi nhận `1=one` tại lúc lấy. Dùng API map để cập nhật, đồng thời cân nhắc xung đột nếu nhiều tác vụ cùng sửa.

### Bài 7 — Phép bằng và quyền sửa

`new SimpleEntry<>("K", 1)` bằng `Map.entry("K", 1)`. Có suy cả hai cùng cho `setValue` không?

**Đáp án:** không. Phép bằng xét cùng khóa và giá trị, không xét quyền sửa hay nguồn gốc. Cặp thứ nhất sửa cục bộ được, cặp factory không cho đổi value. Đừng dùng equals hoặc == để suy quyền thao tác.

### Bài 8 — Ảnh chụp và cập nhật có điều kiện

Bạn giữ cặp độc lập `K=10`. Nguồn sau đó đổi thành `K=12`. Một tác vụ dùng cặp cũ để `put(K, 11)`. Sao chép entry đã ngăn ghi đè dữ liệu mới chưa?

**Đáp án:** chưa. Sao chép tách quan hệ sống và giữ dữ liệu đã đọc, không giữ khóa hay giải quyết xung đột cập nhật. Cần chính sách giá trị kỳ vọng, phiên bản hoặc cơ chế cập nhật đồng thời phù hợp với yêu cầu.

Khi luyện thêm, hãy ghi rõ mỗi entry trong chương trình thuộc loại nào trước khi gọi một phương thức: đang duyệt nguồn, cặp độc lập sửa được, hay cặp độc lập không sửa được. Sau đó xét riêng liệu khóa/value có chứa đối tượng còn sửa được hay không. Hai bước này giúp bạn sử dụng cặp khóa–giá trị đúng vòng đời và đúng quyền sở hữu.
