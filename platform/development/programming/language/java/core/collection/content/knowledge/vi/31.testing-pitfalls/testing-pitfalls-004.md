# ConcurrentModificationException và thay đổi nguồn qua nhiều đường

## 1. Ngoại lệ nói điều gì và không nói điều gì?

`ConcurrentModificationException` (CME) báo rằng một thao tác đã phát hiện sự thay đổi không được phép của đối tượng đang được sử dụng. Tình huống thường gặp là iterator đang duyệt một collection, còn cấu trúc nguồn bị thay đổi bằng một đường khác.

Tên ngoại lệ dễ khiến người mới chỉ nghĩ đến nhiều luồng. Thực tế, một luồng cũng có thể gây CME: vòng lặp đang dùng iterator, nhưng chính mã trong vòng lặp hoặc hàm được gọi lại xóa/thêm vào collection nguồn.

Cơ chế dừng sớm khi phát hiện sai lệch này thường được gọi là **fail-fast**. Nó hỗ trợ phát hiện lỗi, không phải khóa, giao dịch hay cơ chế bảo đảm an toàn giữa các luồng. Việc phát hiện chỉ mang tính nỗ lực tốt nhất; chương trình không được dựa vào việc chắc chắn có CME để hoạt động đúng. [Tài liệu ConcurrentModificationException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ConcurrentModificationException.html).

Bài này tập trung vào một câu hỏi khi gỡ lỗi: **iterator đang duyệt cấu trúc nào, và những đường nào khác có thể thay đổi chính cấu trúc đó?**

## 2. Mô hình nguồn và trạng thái kỳ vọng của iterator

Ở một số triển khai phổ biến như `ArrayList` của OpenJDK, collection theo dõi thay đổi cấu trúc bằng một bộ đếm. Iterator giữ một giá trị kỳ vọng tương ứng. Khi tới điểm kiểm tra, nếu hai giá trị không khớp, iterator có thể ném CME.

```text
Tạo iterator
  nguồn có trạng thái thay đổi M
  iterator ghi nhận kỳ vọng M

Sửa nguồn qua đường ngoài iterator đó
  nguồn chuyển sang trạng thái M'
  iterator vẫn giữ kỳ vọng M

Iterator tiếp tục ở điểm kiểm tra
  trạng thái hiện tại khác kỳ vọng -> phát hiện sai lệch -> CME
```

Các tên `modCount`, `expectedModCount` và vị trí kiểm tra cụ thể là chi tiết triển khai, không phải một giao thức công khai để ứng dụng tự điều chỉnh. Không dùng reflection để sửa bộ đếm hoặc “đồng bộ lại” iterator. [Mã nguồn ArrayList của OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayList.java).

Điểm quan trọng là **iterator riêng nào được phép thay đổi nguồn**. Với iterator hỗ trợ `remove`, xóa qua chính iterator đó có cách cập nhật trạng thái nội bộ phù hợp. Xóa qua một iterator khác vẫn là thay đổi từ bên ngoài đối với iterator đang xét.

### Không phải mọi điểm đều kiểm tra ngay

Không suy rằng dòng `add` hoặc `remove` phải là nơi ném lỗi. Thay đổi có thể đã xảy ra trước đó; ngoại lệ chỉ lộ khi `next`, một thao tác duyệt tiếp theo hoặc một kiểm tra cuối của thao tác hàng loạt phát hiện.

Cũng không suy rằng gọi `hasNext()` không lỗi thì `next()` chắc chắn hợp lệ sau một thay đổi ngoài hợp đồng. Vị trí kiểm tra phụ thuộc triển khai. Một đường chạy kết thúc sớm mà không gặp CME chưa chứng minh cách thay đổi đó hợp lệ.

## 3. “Thay đổi cấu trúc” không chỉ là đổi size

Với `ArrayList`, thêm/xóa phần tử là thay đổi cấu trúc; thay giá trị một vị trí bằng `set` không phải thay đổi cấu trúc theo mô tả của lớp. Iterator fail-fast của lớp được thiết kế để phát hiện các thay đổi cấu trúc ngoài đường sửa được hỗ trợ. [Tài liệu ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

Tuy nhiên không dùng quy tắc “size giữ nguyên nên an toàn” cho mọi thao tác:

| Thao tác điển hình | Điều cần hiểu |
| --- | --- |
| Thêm rồi xóa để size trở lại như cũ | Nguồn vẫn đã trải qua thay đổi; không phục hồi tính hợp lệ của iterator cũ |
| `ArrayList.set(index, value)` | Không phải thay đổi cấu trúc; không biến iterator thành bản chụp dữ liệu |
| `ArrayList.sort(...)` | Có thể làm iterator cũ bị phát hiện sai lệch trong triển khai OpenJDK, dù số phần tử không đổi |
| Thêm khóa mới vào Map | Thay đổi tập ánh xạ |
| Chỉ thay giá trị của khóa đang có trong `HashMap` | Khác với thêm/xóa ánh xạ; vẫn không tạo bảo đảm về bản chụp hoặc đồng bộ |
| `get` trên `LinkedHashMap` theo thứ tự truy cập | Có thể đổi thứ tự liên kết và ảnh hưởng iterator |
| Sửa trường bên trong một phần tử | Không nhất thiết đổi cấu trúc collection; có thể gây vấn đề hash/thứ tự riêng mà CME không phát hiện |

Phải đọc hợp đồng của lớp triển khai và thao tác cụ thể. Không đồng nhất “không tạo CME” với “kết quả không đổi”, “có thể chạy nhiều luồng” hoặc “đúng yêu cầu nghiệp vụ”.

## 4. Những đường cùng đi về một nguồn

### 4.1. Hai biến không có nghĩa hai collection

```java
List<String> first = new ArrayList<>(List.of("A", "B"));
List<String> second = first;
```

`first` và `second` là hai đường tham chiếu đến cùng đối tượng. Thay đổi `second` là thay đổi nguồn của iterator lấy từ `first`. Việc đặt tên biến là `copy`, `backup` hay `readOnly` không quyết định có sao chép dữ liệu hay không.

### 4.2. View của List và Map

Một view là cách nhìn vào dữ liệu được giữ ở nơi khác, không mặc định là bản sao:

```text
List gốc <---- subList
    ^
    +-------- wrapper không cho sửa
    +-------- nhiều iterator

Map gốc <----- keySet
    ^
    +--------- values
    +--------- entrySet
```

Thay đổi thông qua view có thể đi xuyên về nguồn. Ví dụ `map.keySet().remove(key)` xóa ánh xạ trong Map, vì thế iterator đang duyệt `entrySet` của Map đó có thể bị vô hiệu hóa. Các view không phải những kho dữ liệu tách biệt. [Tài liệu Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#keySet()).

Với `subList`, thay đổi được hỗ trợ qua chính view có tác động lên List gốc. Nếu List gốc bị sửa cấu trúc bằng cách khác thay vì qua subList, ngữ nghĩa của subList không còn được xác định theo hợp đồng. Một triển khai có thể báo CME khi dùng view đã mất hiệu lực, nhưng không viết logic ứng dụng yêu cầu mọi triển khai phải báo đúng ngoại lệ đó. Khi cần một phần dữ liệu độc lập về cấu trúc, tạo bản sao thay vì tiếp tục dùng view cũ. [Tài liệu List.subList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#subList(int,int)).

### 4.3. Wrapper không cho sửa vẫn đọc nguồn đang thay đổi

`Collections.unmodifiableList(source)` ngăn sửa qua wrapper, nhưng không ngăn mã khác giữ `source` rồi thay đổi nó. Iterator từ wrapper vẫn dựa vào dữ liệu phía sau. Vì vậy “không thể sửa qua biến này” không có nghĩa “không ai có thể sửa nguồn”.

Muốn tách cấu trúc tại một thời điểm, có thể tạo `new ArrayList<>(source)` hoặc chọn một phép sao chép phù hợp. Bản sao đó vẫn thường dùng chung tham chiếu tới phần tử; nó không tự sao chép sâu trạng thái của từng phần tử.

### 4.4. Hàm được gọi lại và lời gọi lồng

Đoạn sau là mã minh họa sai; `notifyListener` đại diện cho hàm trong ứng dụng:

```java
for (Listener listener : listeners) {
    notifyListener(listener); // có thể gián tiếp gọi listeners.remove(...)
}
```

Nhìn vào thân vòng lặp không thấy `remove` chưa đủ để loại trừ thay đổi. Cần lần theo những hàm, sự kiện hoặc phương thức tiện ích giữ cùng List. Một listener tự đăng ký/hủy đăng ký trong khi đang được thông báo là tình huống thường gặp.

Tương tự, `list.forEach`, `removeIf`, một mapping function hoặc một stream có thể gọi mã tùy biến. Hàm đó không nên tự thêm/xóa nguồn đang được thao tác nếu API không cho phép. Ghi nhận ý định thay đổi để áp dụng sau, hoặc chọn chính sách duyệt có bản chụp khi yêu cầu cho phép.

### 4.5. Một thao tác trông như đọc cũng có thể đổi cấu trúc liên quan

`LinkedHashMap` được cấu hình `accessOrder = true` duy trì thứ tự theo truy cập. `get` một khóa có thể chuyển ánh xạ sang vị trí mới. Vì vậy duyệt `keySet` rồi gọi `get` trên chính Map để lấy giá trị có thể gây CME nếu truy cập làm đổi thứ tự.

Nếu cần khóa và giá trị khi duyệt, cân nhắc duyệt `entrySet` và đọc giá trị của entry theo hợp đồng phù hợp, thay vì tạo truy cập đổi thứ tự không cần thiết. Không áp hành vi của Map theo thứ tự chèn cho Map theo thứ tự truy cập. [Tài liệu LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

## 5. Chương trình Java 17+ tái hiện các đường thay đổi

Lưu thành `CmePathsDemo.java`. Chương trình chạy một luồng, không dùng `sleep` hoặc tranh chấp thời điểm. Các dòng CME minh họa hành vi fail-fast của những triển khai JDK cụ thể được khởi tạo trong mã, như `ArrayList` và `LinkedHashMap`; không phải lời hứa rằng mọi collection hoặc mọi vi phạm đều báo CME.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

public class CmePathsDemo {
    static void expectCme(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected CME for demonstration: " + label);
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + "=CME");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C"));
        List<String> alias = source;
        Iterator<String> aliasCursor = source.iterator();
        alias.add("D");
        expectCme("alias next", aliasCursor::next);

        List<String> parent = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> window = parent.subList(1, 3);
        Iterator<String> parentCursor = parent.iterator();
        window.remove("B");
        System.out.println("parent after view remove=" + parent);
        expectCme("parent iterator after view edit", parentCursor::next);

        List<String> backing = new ArrayList<>(List.of("A", "B"));
        List<String> readOnly = Collections.unmodifiableList(backing);
        Iterator<String> readOnlyCursor = readOnly.iterator();
        backing.add("C");
        expectCme("read-only view iterator", readOnlyCursor::next);

        Map<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        Iterator<Map.Entry<String, Integer>> entries = map.entrySet().iterator();
        map.keySet().remove("B");
        expectCme("entry iterator after keySet edit", entries::next);

        List<String> shared = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> first = shared.iterator();
        Iterator<String> second = shared.iterator();
        first.next();
        first.remove();
        System.out.println("same iterator continues=" + first.next());
        expectCme("other iterator after remove", second::next);

        List<String> replacement = new ArrayList<>(List.of("A", "B"));
        Iterator<String> replacementCursor = replacement.iterator();
        replacement.set(0, "Z");
        System.out.println("ArrayList set then next=" + replacementCursor.next());

        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4, 5));
        Iterator<Integer> numberCursor = numbers.iterator();
        while (numberCursor.hasNext()) {
            if (numberCursor.next() % 2 == 0) {
                numberCursor.remove();
            }
        }
        System.out.println("iterator filtered=" + numbers);

        List<Integer> bulk = new ArrayList<>(List.of(1, 2, 3, 4, 5));
        bulk.removeIf(number -> number % 2 == 0);
        System.out.println("removeIf filtered=" + bulk);

        List<String> editable = new ArrayList<>(List.of("A", "C"));
        ListIterator<String> editCursor = editable.listIterator();
        editCursor.next();
        editCursor.add("B");
        editCursor.next();
        editCursor.set("Z");
        System.out.println("ListIterator edited=" + editable);

        List<String> original = new ArrayList<>(List.of("A", "B"));
        List<String> snapshot = new ArrayList<>(original);
        for (String value : snapshot) {
            original.add(value + "*");
        }
        System.out.println("snapshot=" + snapshot);
        System.out.println("original after processing=" + original);

        Map<String, Integer> accessOrdered = new LinkedHashMap<>(16, 0.75f, true);
        accessOrdered.put("A", 1);
        accessOrdered.put("B", 2);
        accessOrdered.put("C", 3);
        Iterator<String> accessCursor = accessOrdered.keySet().iterator();
        accessOrdered.get("A");
        expectCme("access-order get", accessCursor::next);
        System.out.println("keys after access=" + accessOrdered.keySet());

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> oldSnapshot = copyOnWrite.iterator();
        copyOnWrite.add("C");
        List<String> seen = new ArrayList<>();
        oldSnapshot.forEachRemaining(seen::add);
        System.out.println("copy-on-write iterator=" + seen);
        System.out.println("copy-on-write current=" + copyOnWrite);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CmePathsDemo.java
java CmePathsDemo
```

Stdout của ví dụ trên các triển khai OpenJDK thông dụng tương ứng:

```text
alias next=CME
parent after view remove=[A, C, D]
parent iterator after view edit=CME
read-only view iterator=CME
entry iterator after keySet edit=CME
same iterator continues=B
other iterator after remove=CME
ArrayList set then next=Z
iterator filtered=[1, 3, 5]
removeIf filtered=[1, 3, 5]
ListIterator edited=[A, B, Z]
snapshot=[A, B]
original after processing=[A, B, A*, B*]
access-order get=CME
keys after access=[B, C, A]
copy-on-write iterator=[A, B]
copy-on-write current=[A, B, C]
```

### Đọc từng nhóm kết quả

- `alias` thay đổi cùng đối tượng với `source`, nên iterator cũ phát hiện sai lệch khi tiếp tục.
- Xóa qua `window` là thay đổi qua subList và sửa List cha. Iterator đã tạo trước trên List cha không được cập nhật theo iterator của view.
- Wrapper không cho sửa không bảo vệ iterator khỏi thay đổi được thực hiện qua `backing`.
- `keySet` và `entrySet` dùng chung Map; sửa qua view này ảnh hưởng việc duyệt view kia.
- `first.remove()` hợp lệ cho chính `first`, nhưng không làm iterator `second` trở nên hợp lệ sau thay đổi.
- `ArrayList.set` không làm thay đổi cấu trúc trong trường hợp minh họa; iterator đọc giá trị `Z` hiện tại, chứ không giữ bản chụp giá trị `A` ban đầu.
- Các bản lọc bằng iterator của chính vòng duyệt và `removeIf` cho cùng kết quả mong muốn.
- `ListIterator` cho phép thêm/thay trong trạng thái hợp lệ của chính nó.
- Duyệt bản sao không duyệt trực tiếp cấu trúc `original`; thêm vào `original` không đổi cấu trúc bản sao.
- `get("A")` của Map theo thứ tự truy cập chuyển `A` về cuối; nguồn không cần đổi số phần tử để iterator phát hiện thay đổi.
- Iterator `CopyOnWriteArrayList` vẫn thấy `A`, `B`, còn List hiện tại đã có `C` theo chính sách bản chụp của lớp.

Hàm `expectCme` cố ý bắt ngoại lệ để trình bày thí nghiệm và dừng bằng `AssertionError` nếu không thấy hành vi được mong đợi ở ví dụ đó. Đây không phải mẫu xử lý lỗi nghiệp vụ để đưa vào vòng lặp ứng dụng.

## 6. Chọn cách sửa theo mục đích thay đổi

### 6.1. Xóa phần tử đang duyệt: dùng chính iterator hỗ trợ remove

```java
Iterator<Item> cursor = items.iterator();
while (cursor.hasNext()) {
    Item item = cursor.next();
    if (shouldRemove(item)) {
        cursor.remove();
    }
}
```

Đoạn này là mẫu áp dụng trong ứng dụng; cần cung cấp kiểu `Item`, `items` và hàm điều kiện. Không gọi thêm `items.remove(item)` bên trong vì đó lại là đường sửa ngoài iterator.

`Iterator.remove` là thao tác tùy chọn; một số iterator không hỗ trợ. Với iterator thông thường có hỗ trợ, cần gọi `next` trước và chỉ `remove` tối đa một lần cho lần `next` đó. Vi phạm trạng thái có thể dẫn tới `IllegalStateException`, khác CME. Không mặc định mọi iterator, đặc biệt iterator bản chụp, đều cho phép xóa. [Tài liệu Iterator.remove](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Iterator.html#remove()).

Không lấy việc `Iterator.remove` hoạt động trong vòng `while` rồi suy rằng có thể gọi nó từ action của `forEachRemaining`. Hợp đồng của `forEachRemaining` không xác định hành vi khi action sửa nguồn, kể cả qua phương thức sửa của iterator, trừ khi triển khai công bố chính sách khác.

### 6.2. Lọc theo điều kiện: dùng removeIf với điều kiện không sửa nguồn

```java
items.removeIf(item -> shouldRemove(item));
```

Điều kiện chỉ quyết định giữ hay bỏ. Không gọi `items.add`, `items.remove` hoặc hàm có tác dụng tương đương lên cùng nguồn từ trong điều kiện. `removeIf` cũng cần collection hỗ trợ thao tác xóa; wrapper không cho sửa có thể ném `UnsupportedOperationException`. [Tài liệu Collection.removeIf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

### 6.3. Cần thêm hoặc thay tại con trỏ: dùng ListIterator khi phù hợp

Với List hỗ trợ, `ListIterator.add`, `set` và `remove` cho phép thay đổi theo trạng thái của chính con trỏ. Quy tắc gọi từng phương thức vẫn phải được tuân thủ. Chúng không cấp quyền cho hàm khác tự do sửa cùng List hoặc giữ các iterator khác tiếp tục dùng sau thay đổi.

### 6.4. Muốn quyết định trước rồi áp dụng sau

Có thể thu thập các thay đổi dự kiến vào collection riêng, kết thúc việc duyệt nguồn rồi áp dụng. Cần giữ đúng ý nghĩa:

- Nếu xóa theo giá trị, `removeAll` có thể xóa mọi phần tử bằng giá trị đó, không chỉ một lần xuất hiện đã chọn.
- Nếu xóa theo chỉ số, các chỉ số sau thay đổi có thể dịch chuyển; phải có chiến lược áp dụng phù hợp.
- Nếu cần thêm phần tử mới nhưng không muốn chúng được xử lý trong lượt hiện tại, danh sách chờ thêm riêng làm rõ ranh giới lượt xử lý.

Không thay một lỗi CME bằng một cách xóa làm mất số lượng bản sao hoặc sai vị trí.

### 6.5. Muốn duyệt tập thành viên tại đầu lượt: dùng bản chụp

Bản sao cấu trúc thích hợp khi yêu cầu là xử lý những phần tử đã có lúc bắt đầu. Thêm/xóa nguồn sau đó không tự thay số thành viên trong bản sao. Tuy nhiên đối tượng phần tử có thể vẫn được chia sẻ và thay đổi.

Nếu nguồn đang được nhiều luồng sửa, thao tác tạo bản sao cũng phải được bảo vệ theo hợp đồng của nguồn. `new ArrayList<>(source)` không tự biến việc đọc một `ArrayList` đang bị sửa không đồng bộ thành thao tác an toàn. `List.copyOf` còn có chính sách không cho phần tử `null`; cần chọn API sao chép đúng dữ liệu.

## 7. Stream và hàm được gọi lại vẫn có nguồn chung

Đổi vòng `for` thành stream không giải quyết sự can thiệp vào nguồn:

```java
// Mã sai về chính sách nguồn; không dùng làm cách xóa.
items.stream().forEach(item -> items.remove(item));
```

Với nguồn không được thiết kế cho thay đổi đồng thời, hàm trong pipeline phải không can thiệp vào nguồn trong lúc pipeline chạy. Kết quả của vi phạm không được bảo đảm chỉ là CME; có thể xuất hiện hành vi sai hoặc ngoại lệ khác. Yêu cầu này có ý nghĩa với cả stream tuần tự lẫn song song. [Tài liệu stream: non-interference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

Cũng không coi thời điểm tạo stream là thời điểm chụp dữ liệu: pipeline thường thực hiện lười và nhiều nguồn gắn việc duyệt muộn. Bài toán “tôi thay List sau khi tạo stream nhưng trước terminal operation” cần đọc chính sách nguồn, không áp nguyên mô hình tạo iterator rồi sửa vào mọi stream.

Một phương án rõ nghĩa là tạo kết quả mới bằng `filter` nếu không cần sửa nguồn, hoặc dùng `removeIf` nếu mục tiêu là xóa trên nguồn và API cho phép. Tác dụng phụ trong predicate vẫn cần tránh theo hợp đồng.

## 8. Nếu thực sự có nhiều luồng

### 8.1. Wrapper đồng bộ cần khóa đúng phạm vi

`Collections.synchronizedList` đồng bộ các phương thức theo chính sách của wrapper, nhưng khi duyệt cần tự đồng bộ cả đoạn duyệt trên đối tượng wrapper theo hướng dẫn API:

```java
List<String> shared = Collections.synchronizedList(new ArrayList<>());
synchronized (shared) {
    for (String value : shared) {
        consume(value);
    }
}
```

Đây là đoạn minh họa, cần hàm `consume`. Các đường truy cập khác phải tuân thủ cùng chính sách; giữ và dùng tham chiếu trực tiếp tới List gốc ngoài wrapper có thể phá sự bảo vệ. Khi duyệt view của một wrapper đồng bộ, phải dùng đúng khóa mà API yêu cầu, không tự chọn khóa của một đối tượng view khác. [Tài liệu Collections.synchronizedList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

Khóa không làm hợp lệ việc chính `consume` sửa cấu trúc nguồn qua đường ngoài iterator trong cùng luồng. Monitor Java cho phép vào lại ở cùng luồng; vì thế callback vẫn có thể gây CME nếu sửa sai cách. Đồng bộ và chính sách thay đổi trong lúc duyệt là hai yêu cầu phải giải quyết đồng thời.

### 8.2. Chọn collection đồng thời theo cách nhìn dữ liệu mong muốn

| Chính sách duyệt | Ví dụ | Cần chấp nhận |
| --- | --- | --- |
| Iterator fail-fast trên collection thông thường | `ArrayList`, các view của Map thông thường | Không sửa nguồn ngoài đường được iterator/API cho phép |
| Iterator bản chụp | `CopyOnWriteArrayList` | Không thấy thay đổi thành viên sau lúc tạo iterator; chi phí ghi cao và iterator không cho sửa |
| Duyệt nhất quán yếu | `ConcurrentHashMap` | Có thể phản ánh trạng thái trong quá trình thay đổi; không phải ảnh chụp nguyên tử của toàn Map |

Iterator `CopyOnWriteArrayList` được bảo đảm không ném CME theo chính sách của nó; các thao tác `remove`, `set`, `add` qua iterator không được hỗ trợ. Đây là lựa chọn cho yêu cầu đọc nhiều hơn ghi rất nhiều, không phải phép đổi lớp để che mọi lỗi. [Tài liệu CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

Các iterator của `ConcurrentHashMap` không ném CME, nhưng việc duyệt không bảo đảm có đúng toàn bộ trạng thái Map tại một thời điểm duy nhất. Không suy thứ tự hoặc danh sách phần tử cố định trong khi có cập nhật đồng thời. Chuỗi nhiều thao tác nghiệp vụ vẫn cần xét tính nguyên tử riêng. [Tài liệu ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 9. Cách gỡ lỗi thay đổi nguồn qua nhiều đường

1. Xác định lớp collection thật và kiểu duyệt: iterator, vòng `for` mở rộng, view, stream hay thao tác có callback.
2. Ghi lại thời điểm iterator/lượt duyệt bắt đầu và dòng phát hiện lỗi. Đừng mặc định dòng stack trace chính là nơi đã sửa nguồn.
3. Vẽ các tham chiếu cùng nguồn: biến khác tên, trường đối tượng, getter trả collection thật, subList, các view Map và wrapper.
4. Lần theo mọi lời gọi trong thân duyệt, nhất là callback, listener, hàm tiện ích và truy cập có thể đổi thứ tự.
5. Phân biệt sửa phần tử với sửa cấu trúc; kiểm tra chính sách của đúng triển khai, không chỉ so size trước/sau.
6. Chọn sửa bằng iterator, thao tác hàng loạt, hai giai đoạn, bản chụp hoặc đồng bộ/collection đồng thời theo kết quả cần có.
7. Kiểm tra lại nội dung và số lần xử lý sau sửa, không chỉ kiểm tra “không còn CME”.

Không bắt CME rồi tiếp tục dùng iterator đã sai lệch. Cũng không tự retry cả lượt duyệt nếu lượt trước đã thực hiện tác dụng phụ như gửi thông báo hoặc cập nhật dữ liệu: retry có thể lặp tác dụng phụ. Chính sách thử lại chỉ đúng khi ứng dụng đã có cách bảo đảm nhất quán và xử lý lặp phù hợp.

## 10. Kiểm thử sau khi sửa

Tách thí nghiệm tái hiện lỗi của một triển khai cụ thể khỏi kiểm thử tính đúng của ứng dụng:

- Thí nghiệm CME nên dùng một luồng và thứ tự lời gọi xác định nếu mục tiêu chỉ là minh họa alias/view; không cần tạo tranh chấp ngẫu nhiên.
- Kiểm thử của bản sửa nên đối chiếu phần tử được giữ/xóa, thứ tự, số lần callback và ảnh hưởng lên nguồn/view.
- Với bản chụp, kiểm tra rõ phần tử thêm sau đầu lượt có được xử lý ngay hay để lượt sau.
- Với thao tác đồng thời, điều phối bằng cơ chế phối hợp như latch/barrier khi cần kiểm soát thứ tự thử nghiệm; không dùng một số mili giây `sleep` để suy chắc lịch chạy.
- Không viết test bắt buộc một cuộc đua không đồng bộ phải luôn ném CME. Fail-fast không đưa ra bảo đảm đó.

Câu hỏi tự kiểm tra:

1. Vì sao sửa `alias` có thể làm iterator từ `source` báo lỗi dù hai tên biến khác nhau?
2. Vì sao xóa bằng iterator thứ nhất có thể hợp lệ cho nó nhưng vô hiệu hóa iterator thứ hai?
3. Wrapper không cho sửa và bản sao cấu trúc khác nhau ở điểm nào?
4. Trong Map theo thứ tự truy cập, vì sao một lời gọi `get` có thể liên quan đến CME?
5. Nếu không còn CME sau khi chuyển sang bản chụp hoặc collection đồng thời, cần kiểm chứng thêm điều gì về tập phần tử được xử lý?

Để giải thích được một lỗi CME, hãy chỉ rõ nguồn dùng chung, đường thay đổi và chính sách duyệt bị vi phạm. Để sửa đúng, hãy quyết định lượt xử lý phải nhìn thấy dữ liệu nào và ai có quyền thay đổi nó.
