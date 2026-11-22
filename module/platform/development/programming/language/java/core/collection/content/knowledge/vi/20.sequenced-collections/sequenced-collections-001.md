# Động lực của SequencedCollection, SequencedSet và SequencedMap

## 1. Vấn đề cần giải quyết: thứ tự đã tồn tại nhưng thiếu một tiếng nói chung

Giả sử ứng dụng quản lý các bước xuất bản một sản phẩm. Có chỗ lưu toàn bộ lịch sử vào danh sách, có chỗ dùng hàng đợi hai đầu để chờ xử lý, có chỗ giữ các bước không trùng theo thứ tự người dùng chọn. Một chức năng xem trước chỉ cần hỏi: “Phần tử đầu là gì, phần tử cuối là gì, và nếu đọc ngược thì thấy gì?”

Đây là cùng một nhu cầu nghiệp vụ, nhưng trước Java 21, lập trình viên phải diễn đạt bằng nhiều nhóm API khác nhau. Danh sách dùng chỉ số; hàng đợi hai đầu có phương thức dành cho đầu và cuối; tập hợp sắp xếp có khái niệm nhỏ nhất và lớn nhất; tập hợp liên kết giữ thứ tự chèn nhưng thiếu API chung để lấy phần tử cuối hay tạo luồng theo chiều ngược.

Khoảng trống nằm ở **khả năng biểu đạt hợp đồng**: Java đã có nhiều cấu trúc giữ thứ tự, nhưng chưa có một giao diện chung đủ chính xác để nói “tập hợp này có thứ tự gặp phần tử xác định và có thể được nhìn từ hai chiều”. Ba giao diện được đưa vào từ Java 21 giải quyết khoảng trống đó: `SequencedCollection`, `SequencedSet` và `SequencedMap`. Tài liệu giới thiệu chính thức mô tả động lực này trong bối cảnh JEP 431. [Oracle: Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html).

Sau bài này, bạn cần giải thích được vì sao ba kiểu mới cần tồn tại, chọn được giao diện cho đầu vào/đầu ra có ý nghĩa về thứ tự, và tránh suy diễn rằng có phương thức mới thì mọi cấu trúc đều sửa được hoặc có cùng chi phí.

**Mốc phiên bản:** các API `Sequenced*` thuộc Java 21 trở lên. Chương trình chính bên dưới dùng Java 21, không thể biên dịch bằng `--release 17`. Đây là thay đổi thư viện chuẩn đã có trong Java 21; ví dụ không cần bật tính năng thử nghiệm.

## 2. Thứ tự gặp phần tử là gì?

**Thứ tự gặp phần tử (encounter order)** là trình tự các phần tử được xem như đứng từ đầu đến cuối khi thao tác tôn trọng thứ tự. Bạn có thể hình dung một dãy thẻ trên bàn:

~~~text
đầu                                      cuối
build              test                  ship
~~~

Trong dãy này, `build` đứng trước `test`, còn `ship` đứng sau `test`. Đọc thuận cho ra `build, test, ship`; đọc ngược cho ra `ship, test, build`. Khái niệm đó nói về quan hệ logic giữa các phần tử, không khẳng định chúng nằm cạnh nhau trong bộ nhớ. Một mảng động, cấu trúc liên kết và cây có thể cùng cung cấp trình tự có ý nghĩa.

`SequencedCollection` dùng trình tự này cho các thao tác như duyệt, chuyển thành mảng và tạo nguồn luồng. Giao diện có đầu/cuối, các thao tác tại hai đầu và `reversed()` để nhận góc nhìn ngược; các thao tác sửa là thao tác tùy chọn. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

### 2.1. Có thứ tự không đồng nghĩa với đã sắp xếp

Hãy đưa lần lượt `ship, build, test` vào ba cấu trúc:

| Cấu trúc và cách dùng | Trình tự quan sát | Điều quyết định trình tự |
| --- | --- | --- |
| `ArrayList`, thêm ở cuối | `ship, build, test` | Vị trí trong danh sách |
| `LinkedHashSet`, dùng `add` thông thường | `ship, build, test` | Thứ tự chèn của các phần tử phân biệt |
| `TreeSet` dùng thứ tự tự nhiên của chuỗi | `build, ship, test` | Phép so sánh giữa các phần tử |

Các cấu trúc đều có thể có thứ tự gặp phần tử, nhưng chỉ hàng cuối là thứ tự do so sánh quyết định. Ví dụ “lấy phần tử đầu” của tập hợp liên kết có thể nghĩa là bước được chọn sớm nhất; với tập hợp sắp xếp, nó là bước nhỏ nhất theo bộ so sánh. Cùng một tên thao tác không xóa đi ý nghĩa của cấu trúc bên dưới.

`TreeSet` sắp xếp theo thứ tự tự nhiên hoặc `Comparator` được cung cấp. Đổi bộ so sánh có thể đổi phần tử đứng đầu dù dữ liệu đầu vào không đổi. [Java 21: TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

### 2.2. Một lần in có vẻ ổn định chưa tạo ra bảo đảm

Một `HashSet` chứa vài chuỗi có thể tình cờ in giống nhau qua nhiều lần chạy. Điều đó không biến nó thành tập hợp có hợp đồng thứ tự chèn. `HashSet` không bảo đảm thứ tự duyệt và không bảo đảm thứ tự ấy giữ nguyên theo thời gian. [Java 21: HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

Tương tự, không lấy một kết quả `HashMap` hiện tại làm bằng chứng rằng khóa đầu tiên luôn là khóa chèn trước. `HashMap` không cung cấp bảo đảm về thứ tự của map. [Java 21: HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

Phân biệt hai phát biểu:

- “Lần chạy này iterator trả về `A` trước `B`” là một quan sát.
- “API của cấu trúc quy định `A` phải xuất hiện trước `B` theo quy tắc đã nêu” là một hợp đồng.

Thiết kế chức năng xuất báo cáo, dựng giao diện hay xử lý ưu tiên phải dựa vào phát biểu thứ hai nếu thứ tự ảnh hưởng kết quả.

## 3. Trước Java 21: cùng một ý định, nhiều cách viết

Bảng dưới mô tả sự phân tán API trước Java 21, với dữ liệu không rỗng:

| Kiểu | Lấy đầu | Lấy cuối | Đọc ngược |
| --- | --- | --- | --- |
| `List` | `get(0)` | `get(size() - 1)` | Vòng lặp chỉ số hoặc `ListIterator` đi lùi |
| `Deque` | `getFirst()` | `getLast()` | `descendingIterator()` |
| `SortedSet` | `first()` | `last()` | Nếu có `NavigableSet` thì có `descendingSet()` |
| `LinkedHashSet` | Iterator lấy phần tử đầu | Thường phải duyệt đến cuối | Thường phải tự tổ chức lại việc duyệt hoặc sao chép |
| `LinkedHashMap` | Duyệt `entrySet()` lấy entry đầu | Thường phải duyệt đến cuối | Chưa có góc nhìn ngược thống nhất ở kiểu map này |

Điểm bất tiện không chỉ là số ký tự. Người đọc phải nhận ra rằng các biểu thức khác nhau này đều đang xử lý **biên của một trình tự**. Một tiện ích dùng chung dễ bị tách thành nhiều nhánh theo kiểu cụ thể.

Ví dụ sau là **đoạn phương thức minh họa cách viết tương thích Java 17**, đặt trong một lớp có các import tương ứng; chưa phải chương trình chạy độc lập:

~~~java
static <E> E lastOfList(java.util.List<E> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException();
    }
    return items.get(items.size() - 1);
}

static <E> E lastByTraversal(java.util.Collection<E> items) {
    var it = items.iterator();
    if (!it.hasNext()) {
        throw new java.util.NoSuchElementException();
    }
    E last = it.next();
    while (it.hasNext()) {
        last = it.next();
    }
    return last;
}
~~~

Phương thức thứ hai lấy phần tử cuối **của lần duyệt hiện tại**. Nó không thể tự tạo ra bảo đảm “cuối theo thứ tự chèn” cho mọi `Collection`. Nếu truyền một `HashSet`, đoạn code vẫn chạy nhưng ý nghĩa nghiệp vụ mà người gọi tưởng có thể không tồn tại.

Với `Deque`, hợp đồng trước đó vốn đã nói rõ hai đầu và có cặp API trả giá trị đặc biệt khi thao tác thất bại. Từ Java 21, `Deque` còn thuộc nhánh `SequencedCollection`; các khả năng riêng như `offerFirst`, `peekFirst` và `pollFirst` vẫn có ý nghĩa của chúng. [Java 21: Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

## 4. Vì sao không dùng Collection hoặc List cho tất cả?

### 4.1. Collection quá rộng nếu thứ tự là một phần của yêu cầu

Xét chữ ký giả định:

~~~java
static void printRoute(java.util.Collection<String> stops) {
    for (String stop : stops) {
        System.out.println(stop);
    }
}
~~~

Phương thức chỉ yêu cầu “một tập hợp phần tử”. Người gọi có thể đưa vào một cấu trúc không có thứ tự bảo đảm. Nếu hàm thực chất cần các điểm dừng theo thứ tự tuyến đường, chữ ký chưa thể hiện hết điều kiện đó; tài liệu và sự cẩn thận của người dùng phải bù vào.

Chuyển sang `SequencedCollection<String>` giúp mô tả trực tiếp rằng đầu vào có trình tự. Một `HashSet<String>` không thể được truyền thẳng vào chữ ký ấy. Trình biên dịch có thể phát hiện sự thiếu phù hợp trước khi chương trình chạy.

Tuy vậy, kiểu này chỉ nói **có một trình tự xác định**. Nó chưa nói trình tự ấy là tuyến đường nghiệp vụ đúng. Một `TreeSet` sắp xếp tên điểm dừng vẫn có thứ tự nhưng có thể sai tuyến. Phải ghi rõ thêm ý nghĩa miền dữ liệu, ví dụ “các điểm dừng theo thứ tự di chuyển”, rồi chọn cấu trúc thỏa điều đó.

### 4.2. List quá hẹp nếu không cần chỉ số và phần tử trùng

Nếu dùng `List` làm tham số, bạn nói rằng danh sách là mô hình phù hợp. Điều này thuận lợi khi cần truy cập vị trí hoặc giữ các lần xuất hiện trùng nhau. Nhưng một hàm chỉ in đầu/cuối và duyệt ngược không nhất thiết cần các đặc điểm đó.

Một tập hợp liên kết loại trùng hoặc tập hợp sắp xếp cũng có thể đáp ứng. Buộc người gọi đổi chúng thành `List` chỉ để qua cửa API làm phát sinh bản sao, cấp phát và một bước diễn giải dữ liệu không cần thiết.

Từ Java 21, `List` vẫn giữ hợp đồng danh sách, đồng thời kế thừa `SequencedCollection` và có `reversed()` trả về `List`. Việc thêm tầng giao diện không thay `List` bằng một mô hình yếu hơn. [Java 21: List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

### 4.3. Kiểu cụ thể làm tiện ích lệ thuộc một cách lưu dữ liệu

Một chữ ký nhận `LinkedHashSet` mô tả chính xác lớp lưu trữ, nhưng có thể ràng buộc quá mức. Nếu chỉ cần tính duy nhất và trình tự, `SequencedSet` biểu đạt đúng nhu cầu hơn. Người gọi có thể cung cấp cách triển khai phù hợp khác mà tiện ích không phải phân nhánh theo tên lớp.

Đây là lợi ích thiết kế quan trọng của ba giao diện: **chọn hợp đồng cần dùng, giữ các lựa chọn triển khai bên ngoài hàm xử lý**. Không phải cứ thay tên lớp thành một giao diện mới là tốt; phải xác định đúng các khả năng mà hàm thực sự cần.

## 5. Ba giao diện chia trách nhiệm như thế nào?

Sơ đồ sau chỉ vẽ các nhánh liên quan, không phải toàn bộ cây Java Collections Framework. Dấu mũi tên chỉ “là kiểu con của”:

~~~text
List ----------------------> SequencedCollection ------> Collection
Deque ---------------------> SequencedCollection

SequencedSet --------------> SequencedCollection
SequencedSet --------------> Set ----------------------> Collection
SortedSet -----------------> SequencedSet
LinkedHashSet implements --> SequencedSet

SequencedMap --------------> Map
SortedMap -----------------> SequencedMap
LinkedHashMap implements --> SequencedMap
~~~

### 5.1. SequencedCollection: cần một trình tự phần tử

Bạn dùng giao diện này khi cần diễn đạt đầu/cuối và chiều duyệt mà không yêu cầu chỉ số hoặc tính duy nhất.

Nhóm thao tác chính:

| Ý định | Phương thức |
| --- | --- |
| Xem đầu/cuối | `getFirst()`, `getLast()` |
| Thêm ở đầu/cuối nếu được hỗ trợ | `addFirst(e)`, `addLast(e)` |
| Lấy bỏ đầu/cuối nếu được hỗ trợ | `removeFirst()`, `removeLast()` |
| Có góc nhìn theo chiều ngược | `reversed()` |

Đó là từ vựng để viết chung thao tác trên nhiều họ dữ liệu. Không cần hỏi đối tượng có phải `List` hay `Deque` chỉ để lấy đầu và cuối.

### 5.2. SequencedSet: tính duy nhất cộng với trình tự

`SequencedSet` vừa là `Set` vừa là `SequencedCollection`. Nó cho phép API nói rằng dữ liệu không lặp phần tử theo hợp đồng của set, đồng thời có thứ tự gặp phần tử.

Điểm cần giữ là phép so sánh bằng: hợp đồng `Set.equals` vẫn bỏ qua thứ tự. Hai set chứa cùng phần tử có thể bằng nhau dù duyệt theo hai chiều khác nhau. Kiểu mới không chuyển phép bằng của set thành phép bằng của danh sách. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

Ví dụ “các thẻ lọc không trùng, hiện theo thứ tự đã chọn” phù hợp với một tập hợp liên kết. Ví dụ “các mã không trùng, luôn theo thứ tự so sánh” phù hợp với một tập hợp sắp xếp. Cả hai có thể được xử lý qua `SequencedSet` khi hàm chỉ quan tâm phần chung, nhưng nơi tạo dữ liệu phải quyết định chính sách thứ tự.

### 5.3. SequencedMap: trình tự của các ánh xạ khóa–giá trị

`Map` không phải `Collection`. Đơn vị của `SequencedMap` là ánh xạ khóa–giá trị, nên giao diện này kế thừa `Map` riêng.

Nó có `firstEntry()`, `lastEntry()`, `pollFirstEntry()`, `pollLastEntry()`, `putFirst(k, v)`, `putLast(k, v)` và `reversed()`. Khi map rỗng, các thao tác lấy hoặc lấy bỏ entry ở hai đầu trả `null`. Entry do bốn phương thức đầu trả về là ảnh chụp của ánh xạ tại lúc gọi, không dùng `setValue` để sửa ánh xạ gốc. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

Bài toán “số lượng theo từng giai đoạn, hiển thị theo thứ tự quy trình” cần cả tra cứu theo khóa và thứ tự. Dùng map có trình tự tránh phải tách thành một map tra cứu cộng với một danh sách khóa rồi tự giữ hai nguồn dữ liệu đồng bộ.

### 5.4. Vì sao cần các view có tên sequenced?

Các kiểu trả về quen thuộc của map là `Set<K>`, `Collection<V>` và `Set<Map.Entry<K,V>>`. Chúng có thể duyệt theo trình tự của map nhưng chữ ký đó không cung cấp trực tiếp toàn bộ từ vựng đầu/cuối/ngược.

Các phương thức mới biểu đạt rõ hơn:

~~~java
java.util.SequencedSet<String> keys = counts.sequencedKeySet();
java.util.SequencedCollection<Integer> values = counts.sequencedValues();
java.util.SequencedSet<java.util.Map.Entry<String, Integer>> entries =
        counts.sequencedEntrySet();
~~~

Đây là đoạn minh họa bên trong một phương thức, giả sử `counts` là `SequencedMap<String,Integer>`.

Giá trị có thể lặp, nên `sequencedValues()` trả `SequencedCollection` chứ không phải `SequencedSet`. View khóa không đủ thông tin giá trị để thêm một ánh xạ mới; không suy từ tên kiểu rằng có thể gọi `addFirst` thành công trên mọi view.

## 6. Sự thống nhất nằm ở hợp đồng, không phải thay tất cả bằng một lớp

Các lớp quen thuộc vẫn có vai trò. Ví dụ, `ArrayList` vẫn là danh sách dựa trên mảng có thể tăng kích thước, có truy cập vị trí và cho phép `null`. Nó được dùng qua giao diện mới nhờ quan hệ kiểu đã được bổ sung, không phải nhờ một bản sao được tự tạo ra. [Java 21: ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

Một hàm báo cáo đầu/cuối có thể viết như sau trong Java 21:

~~~java
static String describeEnds(java.util.SequencedCollection<?> items) {
    if (items.isEmpty()) {
        return "empty";
    }
    return items.getFirst() + " -> " + items.getLast();
}
~~~

Hàm không biết đối tượng lưu bằng mảng, liên kết hay cây. Nó cũng không cần biết có trùng phần tử hay không. Nó chỉ dựa vào hợp đồng đầu/cuối.

Đổi lại, nếu thuật toán cần `get(i)` thì `SequencedCollection` không đủ. Nếu thuật toán cần một hàng đợi giới hạn dung lượng với `offer`/`poll` thì `Deque` hay một kiểu phù hợp khác vẫn cần thiết. Tên mới không phải lý do hạ mọi chữ ký xuống cùng một mức trừu tượng.

Đoạn kiểm tra `isEmpty` rồi lấy hai đầu ở trên dành cho ngữ cảnh không có thay đổi đồng thời trong suốt thao tác. Hai phương thức riêng biệt không tự tạo một ảnh chụp nguyên tử. Nếu nhiều luồng sửa dữ liệu, phải thiết kế cơ chế đồng bộ hoặc ảnh chụp phù hợp với cách triển khai.

## 7. reversed(): đổi hướng nhìn, cần phân biệt với bản sao

Hình dung dữ liệu gốc:

~~~text
gốc:          A   B   C
view ngược:   C   B   A

view.getFirst()  <->  gốc.getLast()
view.getLast()   <->  gốc.getFirst()
~~~

`reversed()` trả **góc nhìn theo chiều ngược (reverse-ordered view)**. Với một `List` như `ArrayList`, sửa qua view được phép có thể ghi xuyên về danh sách gốc. Ví dụ:

~~~java
java.util.List<String> original =
        new java.util.ArrayList<>(java.util.List.of("A", "B", "C"));
java.util.List<String> backwards = original.reversed();
backwards.addFirst("D");
// original: [A, B, C, D]
// backwards: [D, C, B, A]
~~~

Đây là đoạn minh họa Java 21 bên trong phương thức. Thêm ở đầu góc nhìn ngược tương ứng thêm ở cuối hướng gốc. Không có một lệnh “đảo mảng vật lý” được yêu cầu ở đây.

Phải đọc hợp đồng cụ thể khi dựa vào khả năng quan sát thay đổi từ cấu trúc gốc. Giao diện chung nêu rằng mức độ nhìn thấy thay đổi từ nguồn phụ thuộc cách triển khai. Không hứa mọi kiểu `SequencedCollection` đều có cùng đặc tính cập nhật, iterator hay an toàn luồng.

Đối với `LinkedHashMap`, tài liệu lớp quy định rõ thay đổi qua view ngược truyền về map gốc và thay đổi map gốc nhìn thấy qua view; thứ tự truy cập cũng có thể liên quan nếu map được tạo ở chế độ access-order. [Java 21: LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 7.1. Khi nào cần sao chép?

Nếu chức năng cần lưu lại trình tự tại một thời điểm, hãy tạo dữ liệu độc lập về cấu trúc:

~~~java
java.util.List<String> saved =
        new java.util.ArrayList<>(original.reversed());
~~~

`saved` nhận các phần tử theo hướng ngược tại lúc sao chép, rồi không tự đổi cấu trúc khi thêm/xóa vào `original`. Đây vẫn là sao chép nông: nếu phần tử là đối tượng có trạng thái thay đổi, hai cấu trúc có thể cùng giữ tham chiếu đến chúng. Muốn ảnh chụp sâu phải có chính sách riêng cho loại phần tử.

Đừng dùng `reversed()` chỉ vì thấy kết quả ban đầu giống một bản sao đã đảo. Hai lựa chọn có mục đích sở hữu dữ liệu khác nhau.

### 7.2. Luồng ngược trở nên tự nhiên hơn

Một lợi ích thực tế là đưa chiều duyệt vào nguồn dữ liệu:

~~~java
var display = original.reversed().stream().toList();
~~~

Không cần tự chép sang một danh sách rồi đảo danh sách đó chỉ để lấy một luồng đọc ngược. Nếu chuyển sang luồng song song, thứ tự gặp phần tử vẫn là một thuộc tính của nguồn; thứ tự thực thi tác vụ của `forEach` không được bảo đảm theo trình tự đó. Khi cần tác dụng phụ theo thứ tự gặp phần tử, xem `forEachOrdered`; không suy từ `reversed()` rằng mọi luồng chạy song song sẽ in theo thứ tự mong đợi. [Java 21: Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).

## 8. Có thứ tự không có nghĩa là được đặt phần tử tùy ý

Một giao diện chung cần mô tả được cấu trúc sửa được, cấu trúc không sửa được và cấu trúc mà thứ tự bị một quy tắc khác chi phối. Vì vậy, nhiều thao tác sửa là tùy chọn và có thể ném `UnsupportedOperationException`.

### 8.1. Tập hợp liên kết có thể định vị lại một phần tử

Trong `LinkedHashSet`, `add` thông thường với phần tử đã có không đổi thứ tự. `addFirst` và `addLast` có thể đưa phần tử đã có đến đầu hoặc cuối, không tạo một bản trùng.

Ví dụ một bộ thẻ đang là `[ship, build, test]`. Gọi `addFirst("test")` cho ra `[test, ship, build]`; sau đó gọi `add("ship")` vẫn giữ trình tự ấy. Chức năng “ghim lên đầu” được diễn đạt trực tiếp thay cho cách xóa rồi thêm với nhiều quy tắc phụ. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

### 8.2. Tập hợp sắp xếp phải giữ quy tắc so sánh

Giả sử một `TreeSet<Integer>` đang chứa `[10, 20, 30]` theo thứ tự tự nhiên. Cho phép đặt `25` vào đầu sẽ mâu thuẫn với yêu cầu sắp xếp. Vì thế `SortedSet` không hỗ trợ định vị tường minh bằng `addFirst` và `addLast`; các phương thức này ném `UnsupportedOperationException`.

Điều này vẫn đúng khi giá trị bạn định thêm tình cờ đã phù hợp vị trí đầu hoặc cuối. Đừng gọi thử một giá trị “đúng thứ tự” rồi xem đó là cách sử dụng hợp lệ; hãy thêm bằng `add` để cấu trúc tự quyết định vị trí. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

### 8.3. Map sắp xếp có cùng ranh giới

`SortedMap` xác định trình tự theo so sánh khóa. Nó có thể được dùng như `SequencedMap` để xem đầu/cuối/ngược, nhưng `putFirst` và `putLast` không được hỗ trợ vì chúng yêu cầu áp đặt vị trí. `put` vẫn là cách thêm hoặc cập nhật theo quy tắc của map. [Java 21: SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html).

Một `TreeMap` sắp xếp theo khóa, không theo giá trị. Nếu đầu vào là khóa `2` rồi khóa `1`, thứ tự duyệt tự nhiên là `1, 2`; việc dùng `SequencedMap` không biến nó thành thứ tự chèn. [Java 21: TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

### 8.4. Lớp bọc không sửa được vẫn nên giữ thông tin thứ tự

Trước đây, dùng lớp bọc trả `Set` có thể làm chữ ký mất khả năng biểu đạt thứ tự, dù đối tượng bên trong là một tập hợp liên kết.

Java 21 có các hàm:

- `Collections.unmodifiableSequencedCollection(...)`;
- `Collections.unmodifiableSequencedSet(...)`;
- `Collections.unmodifiableSequencedMap(...)`.

Chúng giữ kiểu hợp đồng có trình tự và chặn sửa qua lớp bọc. Chúng là view, không phải lời hứa rằng nguồn sẽ không bao giờ đổi; thao tác truy vấn đọc qua dữ liệu nguồn. [Java 21: Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

Đây là điểm hữu ích cho API trả dữ liệu chỉ đọc: người dùng vẫn biết có thể lấy đầu/cuối và đọc ngược. Nếu yêu cầu là một ảnh chụp độc lập, hãy tạo bản sao có chính sách thứ tự rõ ràng rồi bọc nó; chỉ bọc nguồn sống chưa đạt yêu cầu đó.

## 9. Phép bằng và độ phức tạp không được thống nhất theo tên mới

### 9.1. Trình tự có thể quan trọng khi duyệt nhưng không tham gia equals

`List.equals` so sánh cả phần tử lẫn vị trí tương ứng. Một danh sách `[A, B]` khác `[B, A]`. Trong khi đó `Set.equals` nói về cùng thành viên; thêm khả năng có trình tự không sửa hợp đồng này. [Java 21: Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

Tương tự, `Map.equals` xét cùng các ánh xạ, không xét trình tự duyệt. Một `LinkedHashMap` và view ngược của nó có thể bằng nhau dù báo cáo hai thứ tự khác nhau. [Java 21: Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html).

Vì vậy, nếu kiểm thử cần kiểm chứng **trình tự**, hãy so sánh trình tự được thu thập, chẳng hạn danh sách các khóa. Một kiểm thử chỉ gọi `expectedSet.equals(actualSet)` có thể bỏ sót lỗi thứ tự giao diện.

Cũng không giả định một tham số `SequencedCollection<?>` có phép bằng theo danh sách: nó có thể đang tham chiếu đến set hoặc kiểu khác. Giao diện chung không áp đặt một định nghĩa `equals` duy nhất mâu thuẫn với các nhánh con.

### 9.2. Cùng tên thao tác không có nghĩa cùng chi phí

`getLast` hoặc `addFirst` giúp nói rõ ý định. Nó không tự thay thuật toán lưu trữ của đối tượng thành thuật toán khác.

Ví dụ, thêm vào đầu `ArrayList` phải dịch các phần tử đang có về phía sau. Khi số phần tử tăng, công việc đó tăng theo; đổi `add(0, value)` thành `addFirst(value)` chủ yếu cải thiện cách diễn đạt. Một thuật toán thường xuyên thêm/xóa hai đầu vẫn phải chọn cấu trúc theo khối lượng công việc thực tế.

Đừng viết một hàm tổng quát nhận `SequencedCollection` rồi hứa mọi thao tác hai đầu đều có thời gian hằng số. Muốn đặt cam kết hiệu năng, phải dựa vào tài liệu của cách triển khai và cách sử dụng cụ thể.

## 10. Chương trình đầy đủ: cùng hợp đồng, các chính sách khác nhau

Lưu toàn bộ mã sau vào **`SequencedMotivationDemo.java`**. Chương trình dùng chuỗi ASCII cho stdout để kết quả không phụ thuộc cách hiển thị dấu tiếng Việt trên terminal.

Nó kiểm chứng bốn điều: một hàm nhận được nhiều kiểu có trình tự; đọc ngược khác sao chép; set/map vẫn giữ hợp đồng riêng; thao tác định vị có thể không được hỗ trợ.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedCollection;
import java.util.SequencedMap;
import java.util.SequencedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class SequencedMotivationDemo {
    static String ends(SequencedCollection<?> items) {
        if (items.isEmpty()) {
            return "empty";
        }
        return items.getFirst() + " -> " + items.getLast();
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | java.util.NoSuchElementException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> stages = new ArrayList<>(List.of("build", "test", "ship"));
        Deque<String> jobs = new ArrayDeque<>(List.of("build", "test", "ship"));
        SequencedSet<String> unique =
                new LinkedHashSet<>(List.of("ship", "build", "test", "build"));
        SequencedSet<String> sorted =
                new TreeSet<>(List.of("ship", "build", "test", "build"));

        System.out.println("list ends: " + ends(stages));
        System.out.println("deque ends: " + ends(jobs));
        System.out.println("linked set ends: " + ends(unique));
        System.out.println("sorted set ends: " + ends(sorted));
        System.out.println("reverse stream: " + stages.reversed().stream().toList());

        List<String> backwards = stages.reversed();
        List<String> snapshot = new ArrayList<>(backwards);
        backwards.addFirst("archive");
        System.out.println("list after reverse addFirst: " + stages);
        System.out.println("reverse view now: " + backwards);
        System.out.println("reverse copy stays: " + snapshot);

        unique.addFirst("test");
        unique.add("ship");
        System.out.println("set after reposition: " + unique);
        System.out.println("set equals reverse: " + unique.equals(unique.reversed()));
        System.out.println("list equals reverse: " + stages.equals(stages.reversed()));

        SequencedMap<String, Integer> counts = new LinkedHashMap<>();
        counts.put("build", 1);
        counts.put("test", 2);
        counts.put("ship", 3);
        System.out.println("map first: " + counts.firstEntry());
        System.out.println("map reverse first: " + counts.reversed().firstEntry());
        counts.putFirst("test", 20);
        System.out.println("map after putFirst: " + counts);
        System.out.println("map keys: " + counts.sequencedKeySet());
        System.out.println("map values: " + counts.sequencedValues());
        System.out.println("reverse map keys: " + counts.reversed().sequencedKeySet());
        System.out.println("map equals reverse: " + counts.equals(counts.reversed()));

        LinkedHashSet<String> colors =
                new LinkedHashSet<>(List.of("red", "blue"));
        SequencedSet<String> readOnly =
                Collections.unmodifiableSequencedSet(colors);
        colors.addLast("green");
        System.out.println("read-only view sees: " + readOnly);
        System.out.println("read-only add: " + failure(() -> readOnly.addFirst("black")));

        System.out.println("sorted addFirst: " + failure(() -> sorted.addFirst("alpha")));
        SequencedMap<Integer, String> orderedByKey = new TreeMap<>();
        orderedByKey.put(2, "two");
        orderedByKey.put(1, "one");
        System.out.println("sorted map keys: " + orderedByKey.sequencedKeySet());
        System.out.println("sorted map putLast: "
                + failure(() -> orderedByKey.putLast(0, "zero")));

        SequencedCollection<String> empty = new ArrayList<>();
        System.out.println("empty getFirst: " + failure(() -> empty.getFirst()));
        SequencedMap<String, Integer> emptyMap = new LinkedHashMap<>();
        System.out.println("empty map first: " + emptyMap.firstEntry());
    }
}
~~~

Biên dịch bằng JDK 21 trở lên, đặt mức API/ngôn ngữ mục tiêu là 21, sau đó chạy trên Java 21 trở lên:

~~~shell
javac --release 21 -encoding UTF-8 SequencedMotivationDemo.java
java SequencedMotivationDemo
~~~

Không cần `--enable-preview`. Nếu dùng JDK mới hơn để biên dịch, `--release 21` giúp phát hiện việc vô tình sử dụng API chỉ có sau Java 21. Ví dụ này đã được biên dịch với mức release 21 và chạy thành công bằng OpenJDK 24.0.2.

Stdout chính xác:

~~~text
list ends: build -> ship
deque ends: build -> ship
linked set ends: ship -> test
sorted set ends: build -> test
reverse stream: [ship, test, build]
list after reverse addFirst: [build, test, ship, archive]
reverse view now: [archive, ship, test, build]
reverse copy stays: [ship, test, build]
set after reposition: [test, ship, build]
set equals reverse: true
list equals reverse: false
map first: build=1
map reverse first: ship=3
map after putFirst: {test=20, build=1, ship=3}
map keys: [test, build, ship]
map values: [20, 1, 3]
reverse map keys: [ship, build, test]
map equals reverse: true
read-only view sees: [red, blue, green]
read-only add: UnsupportedOperationException
sorted addFirst: UnsupportedOperationException
sorted map keys: [1, 2]
sorted map putLast: UnsupportedOperationException
empty getFirst: NoSuchElementException
empty map first: null
~~~

### 10.1. Đọc các nhóm kết quả theo ý nghĩa

**Bốn dòng đầu:** cùng một hàm `ends` xử lý `List`, `Deque`, tập hợp liên kết và tập hợp sắp xếp. Hai set nhận cùng dữ liệu ban đầu nhưng đầu/cuối khác nhau vì chính sách thứ tự khác nhau. Chuỗi `build` lặp hai lần không tạo hai phần tử trong set.

**Ba dòng sau thao tác trên view:** `backwards.addFirst("archive")` đưa phần tử về cuối danh sách gốc. View phản ánh hướng ngược mới; `snapshot` vẫn là trình tự đã sao chép trước đó. Chương trình không tạo iterator rồi sửa dữ liệu trong lúc duyệt.

**Các dòng về set:** `test` được chuyển lên đầu; gọi `add("ship")` không di chuyển một phần tử đang có. Set vẫn bằng view ngược theo thành viên. Danh sách không bằng view ngược trong dữ liệu này vì các vị trí không tương ứng.

**Các dòng về map:** map ban đầu theo thứ tự chèn. `putFirst("test", 20)` vừa cập nhật giá trị khóa đã có vừa đưa ánh xạ đó lên đầu. View khóa và view giá trị đi theo cùng trình tự ánh xạ; view ngược đổi chiều của cả chúng.

**Nhóm cuối:** nguồn của lớp bọc chỉ đọc được thêm `green` nên view nhìn thấy phần tử ấy. Sửa qua lớp bọc bị chặn. Set/map sắp xếp từ chối định vị tường minh, dù vẫn có thứ tự để đọc. Collection rỗng và map rỗng dùng quy ước trả kết quả khác nhau ở các phương thức được minh họa.

### 10.2. Vì sao chương trình không thử in thứ tự HashSet?

Mục tiêu là chứng minh một hợp đồng có thể dựa vào, không chọn một kết quả ngẫu nhiên rồi học thuộc. Một lần in `HashSet` không đủ chứng minh hay phủ định yêu cầu thứ tự nghiệp vụ. Ở đây, sự khác biệt thể hiện ngay ở khả năng truyền vào `ends`: một `HashSet` không thuộc kiểu tham số này.

## 11. Cách đưa vào thiết kế API thực tế

Hãy bắt đầu từ câu mà nghiệp vụ muốn nói, rồi mới chọn giao diện:

| Nhu cầu của hàm | Kiểu có thể phù hợp | Điều vẫn phải xác định thêm |
| --- | --- | --- |
| Duyệt phần tử, không quan tâm trình tự | `Collection<E>` | Tính trùng, khả năng sửa, điều kiện phần tử |
| Xem đầu/cuối, đọc hai chiều | `SequencedCollection<E>` | Ý nghĩa trình tự, dữ liệu rỗng, quyền sửa |
| Cần vị trí `i` hoặc ngữ nghĩa danh sách | `List<E>` | Chi phí truy cập và cập nhật của triển khai |
| Không trùng, có trình tự | `SequencedSet<E>` | Thứ tự chèn, so sánh hay chính sách khác |
| Tra cứu theo khóa và trình tự ánh xạ | `SequencedMap<K,V>` | Chính sách thứ tự, xử lý khóa/giá trị `null` |
| Quy trình hàng đợi hai đầu | `Deque<E>` | Hành vi rỗng, giới hạn dung lượng, đồng thời |

Một ví dụ trả về “các bộ lọc được chọn, không trùng và hiện theo thứ tự người dùng chọn” có thể dùng `SequencedSet<Filter>` với dữ liệu được tạo bằng `LinkedHashSet`, rồi bọc thành view chỉ đọc có cùng kiểu nếu phù hợp vòng đời.

Một ví dụ báo cáo “các chỉ số theo khóa tăng dần” có thể dùng `SortedMap` hoặc `NavigableMap` nếu người dùng API còn cần bộ so sánh hay truy vấn phạm vi. Nếu chỉ cần đầu/cuối và duyệt, `SequencedMap` có thể là mức hợp đồng đủ dùng. Không giấu một khả năng mà người dùng thực sự cần chỉ để dùng tên mới.

Nếu thay chữ ký của một API đang được công bố, đó vẫn là quyết định tương thích cần xem xét. Việc một lớp trong JDK có thêm quan hệ kiểu không cho phép bạn tùy tiện đổi mọi tham số, kiểu trả về hoặc yêu cầu phiên bản của thư viện đang được người khác dùng.

### 11.1. Không ép kiểu để “tạo” thứ tự

Đoạn dưới là **ví dụ không hợp lệ khi chạy**, không thuộc chương trình chính:

~~~java
java.util.Collection<String> source = new java.util.HashSet<>();
java.util.SequencedCollection<String> ordered =
        (java.util.SequencedCollection<String>) source;
~~~

Một phép ép kiểu không bổ sung hợp đồng mà đối tượng không triển khai. Đối tượng `HashSet` này sẽ gây `ClassCastException` ở phép ép kiểu.

Nếu đầu vào thực sự không có thứ tự nghiệp vụ, phải quyết định chính sách chuyển đổi. Chép sang `ArrayList` chỉ giữ thứ tự duyệt quan sát được lúc chép; chép sang `TreeSet` tạo thứ tự theo so sánh và loại trùng. Hai phép chuyển đổi có ý nghĩa khác nhau, không phải cách sửa kiểu có thể thay nhau vô điều kiện.

### 11.2. Xác định riêng hành vi rỗng

Một hàm trả “đầu/cuối” phải quyết định đầu vào rỗng là hợp lệ, trả kết quả không có dữ liệu hay báo lỗi miền nghiệp vụ. Chương trình minh họa `ends` trả chuỗi `empty`; đây là lựa chọn của hàm, không phải quy tắc bắt buộc của `SequencedCollection`.

Đừng viết mọi helper bằng cách bắt `Exception` rồi trả `null`. Cách đó có thể che cả lỗi không hỗ trợ thao tác, lỗi dữ liệu và lỗi lập trình. Kiểu đầu vào có trình tự giúp biểu đạt một khía cạnh; chính sách thất bại vẫn cần được thiết kế rõ.

## 12. Những hiểu nhầm dễ dẫn đến thiết kế sai

1. **“Java 21 mới có collection có thứ tự.”** Các cấu trúc có thứ tự đã tồn tại từ trước. Phần mới là tầng giao diện và bộ thao tác thống nhất để biểu đạt, sử dụng phần chung ấy.
2. **“Sequenced nghĩa là tăng dần.”** Một danh sách theo thứ tự người dùng chọn cũng có trình tự. Quy tắc so sánh là một khả năng riêng của nhóm sorted.
3. **“Mọi Set trở thành SequencedSet.”** Chỉ các kiểu phù hợp mới cung cấp hợp đồng ấy. Đừng dùng thứ tự tình cờ của một cấu trúc không bảo đảm thứ tự.
4. **“Có addFirst là gọi luôn được.”** Thao tác sửa có thể bị từ chối bởi lớp bọc hoặc quy tắc sắp xếp.
5. **“reversed đã chép dữ liệu.”** View và bản sao có quyền sở hữu/vòng đời khác nhau. Tự tạo bản sao khi cần dữ liệu độc lập về cấu trúc.
6. **“Cùng thứ tự là đủ, không cần quan tâm trùng.”** `SequencedCollection` không bảo đảm tính duy nhất; `SequencedSet` mới kết hợp hợp đồng set.
7. **“equals sẽ kiểm tra cả thứ tự của set/map.”** Kiểu mới giữ hợp đồng equals của các nhánh đó. Kiểm chứng thứ tự bằng một biểu diễn có thứ tự thích hợp.
8. **“Phương thức gọn hơn làm mọi thao tác nhanh hơn.”** Tên API không thay cấu trúc mảng, liên kết hay cây bên dưới.
9. **“Chỉ đọc là ảnh chụp cố định.”** Lớp bọc view chặn sửa qua một đường truy cập; nguồn bên dưới có thể tiếp tục đổi.
10. **“Đã dùng giao diện mới thì chạy được trên Java 17.”** Thư viện chuẩn được nhắm tới phải có các kiểu ấy. Cần thống nhất mức JDK biên dịch, mục tiêu release và runtime.

## 13. Thực hành có đáp án

### Bài 1 — Chọn chữ ký cho một tiện ích

Một hàm chỉ cần hiển thị phần tử đầu, phần tử cuối và các phần tử theo chiều ngược. Nó phải nhận được danh sách, hàng đợi hai đầu và tập hợp liên kết. Chọn một tham số chung trong Java 21, rồi nêu hai điều kiểu đó chưa cam kết.

**Đáp án:** dùng `SequencedCollection<? extends E>` hoặc `SequencedCollection<?>` tùy cách dùng phần tử. Kiểu không nói trình tự ấy là thứ tự chèn, không cam kết cho phép sửa; cũng không cam kết không trùng, độ phức tạp hay đồng bộ. Nếu hàm chỉ đọc thì không nên tự thêm yêu cầu sửa vào hợp đồng.

### Bài 2 — Thứ tự và nghiệp vụ

Một hàm in các điểm dừng của tuyến xe nhận `SequencedCollection<String>`. Người gọi đưa `TreeSet` tên điểm dừng theo bảng chữ cái. Trình biên dịch chấp nhận. Có thể kết luận tuyến đường đúng không?

**Đáp án:** chưa. Kiểu bảo đảm có trình tự nhưng không xác định trình tự ấy là lịch di chuyển. Cần hợp đồng miền dữ liệu và nguồn dữ liệu đúng; tên tham số hoặc tài liệu phải nêu “theo thứ tự tuyến đường”, rồi chọn cấu trúc bảo toàn quy tắc đó.

### Bài 3 — Dự đoán view và bản sao

Bắt đầu `List<Integer> a = new ArrayList<>(List.of(2, 4, 6))`. Lấy `r = a.reversed()` và `saved = new ArrayList<>(r)`. Sau đó `r.addFirst(8)`. Ba trình tự là gì?

**Đáp án:** `a` là `[2, 4, 6, 8]`; `r` là `[8, 6, 4, 2]`; `saved` là `[6, 4, 2]`. Đây là các phần tử `Integer` không đổi trạng thái, nên ví dụ không có vấn đề dùng chung đối tượng có thể sửa.

### Bài 4 — Tính duy nhất và định vị

Một `LinkedHashSet` có `[A, B, C]`. Gọi `add("B")` rồi `addLast("A")`. Có bốn phần tử không? Trình tự cuối thế nào?

**Đáp án:** vẫn ba phần tử. `add("B")` giữ vị trí của `B`; `addLast("A")` chuyển `A` xuống cuối, kết quả `[B, C, A]`. Không đưa quy tắc này sang `TreeSet`; thao tác định vị tường minh bị từ chối ở tập hợp sắp xếp.

### Bài 5 — Kiểm thử thứ tự map

Hai map có cùng ánh xạ nhưng khóa được duyệt theo hai thứ tự khác nhau. Một kiểm thử dùng `expected.equals(actual)` vẫn qua. Phải bổ sung gì nếu thứ tự là yêu cầu giao diện?

**Đáp án:** so sánh trình tự khóa hoặc entry, ví dụ tạo `new ArrayList<>(actual.sequencedKeySet())` rồi so với danh sách mong đợi. Đừng đổi hợp đồng `Map.equals` bằng suy đoán; hãy kiểm thử trực tiếp điều nghiệp vụ quan tâm.

### Bài 6 — Sửa lỗi lựa chọn thao tác

Một `SequencedMap<Integer,String>` thực tế là `TreeMap`. Lập trình viên gọi `putFirst(0, "start")` vì `0` nhỏ nhất và gặp lỗi. Cách sửa phù hợp là gì?

**Đáp án:** dùng `put(0, "start")` để map sắp xếp theo khóa. `putFirst` vẫn không được hỗ trợ ngay cả khi khóa tình cờ phù hợp đầu. Nếu nghiệp vụ cần tự ghim một khóa bất kỳ lên đầu, phải xem lại lựa chọn cấu trúc và chính sách thứ tự, chẳng hạn một map liên kết; không bắt lỗi rồi giả vờ thao tác đã thành công.

### Bài 7 — Chỉ đọc hay ảnh chụp?

API tạo `Collections.unmodifiableSequencedSet(source)` rồi trả về cho giao diện. Một phần khác của ứng dụng thêm phần tử vào `source`. Có thể hứa kết quả trả về không đổi không?

**Đáp án:** không thể đưa lời hứa ấy chỉ từ lớp bọc. Nếu cần một ảnh chụp có thứ tự độc lập về cấu trúc, hãy tạo bản sao riêng có chính sách đúng rồi bọc bản sao; nếu phần tử có trạng thái thay đổi, phải giải quyết thêm mức sao chép cần thiết.

### Bài 8 — Tự kiểm chứng mức phiên bản

Thử biên dịch chương trình chính với `javac --release 17`, sau đó với `javac --release 21` trên JDK hỗ trợ. Vì sao lần đầu không phù hợp, và vì sao chỉ nâng runtime chưa đủ cho một pipeline đang biên dịch mục tiêu 17?

**Đáp án:** API `Sequenced*` không thuộc thư viện chuẩn Java 17. `--release` kiểm soát API/ngôn ngữ mục tiêu khi biên dịch; một runtime mới hơn không làm các kiểu Java 21 xuất hiện trong mục tiêu release 17. Phải thống nhất yêu cầu Java 21+ của phần mã sử dụng các API này, đồng thời kiểm tra sự tương thích mà dự án cần duy trì.

Khi tự sửa chương trình, hãy thêm một cấu trúc mới vào hàm `ends` và giải thích nguồn gốc của thứ tự đầu/cuối trước khi chạy. Kết quả có giá trị học tập khi bạn dự đoán được hợp đồng nào đang được thực thi, không chỉ khi stdout tình cờ giống điều mong đợi.
