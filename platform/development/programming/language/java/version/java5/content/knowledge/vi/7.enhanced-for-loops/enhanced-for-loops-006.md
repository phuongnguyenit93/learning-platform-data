# Thứ tự duyệt phụ thuộc cấu trúc dữ liệu

## 1. `for-each` không tự quyết định thứ tự phần tử

Khi viết:

```java
for (Integer value : source) {
    System.out.println(value);
}
```

vòng lặp lấy các phần tử theo cơ chế mà nguồn cung cấp. Nó không tự sắp xếp, không tự giữ lịch sử thêm phần tử và không biến mọi collection thành một danh sách có thứ tự ổn định.

Với mảng, Java duyệt theo chỉ số tăng dần. Với `Iterable`, Java dùng iterator của đối tượng nguồn. Vì thế, muốn biết thứ tự của một vòng lặp, phải đọc hợp đồng của cấu trúc dữ liệu và cách cấu trúc đó được tạo/cấu hình.

Một chương trình in cùng thứ tự trong vài lần chạy chưa đủ để coi thứ tự đó là cam kết của API. Cần phân biệt **thứ tự quan sát được** với **thứ tự được hợp đồng bảo đảm**.

## 2. Những loại thứ tự dễ bị nhầm

- **Thứ tự vị trí:** phần tử ở vị trí nào thì được gặp ở vị trí đó, như mảng hoặc `List`.
- **Thứ tự thêm vào:** phản ánh quá trình đưa phần tử/khóa vào một cấu trúc có giữ thứ tự đó.
- **Thứ tự so sánh:** được xác định bởi thứ tự tự nhiên hoặc `Comparator`.
- **Thứ tự truy cập:** có thể thay đổi khi truy cập phần tử trong một cấu hình cấu trúc cụ thể.
- **Không được quy định:** API không cam kết một thứ tự mà chương trình có thể dựa vào.

Thuật ngữ **thứ tự gặp (encounter order)** mô tả trình tự phần tử được cung cấp khi duyệt. Cần hỏi thêm thứ tự gặp đó được duy trì theo vị trí, thao tác thêm, comparator hay một chính sách khác.

“Không được quy định” không có nghĩa mỗi lần duyệt phải ngẫu nhiên khác nhau. Nó có nghĩa chương trình không được dùng một thứ tự tình cờ quan sát thấy làm tiền đề đúng đắn.

## 3. Bảng đọc nhanh theo nguồn

| Nguồn đang duyệt | Cam kết cần biết |
| --- | --- |
| Mảng | Theo chỉ số `0` đến `length - 1` |
| `List` | Theo thứ tự phần tử của list, tương ứng vị trí tăng dần khi dùng iterator thông thường |
| `HashSet` | Không bảo đảm thứ tự duyệt |
| `LinkedHashSet` | Có thứ tự gặp; với thao tác `add` thông thường là thứ tự thêm mới |
| `TreeSet` | Theo thứ tự tự nhiên hoặc comparator đã cấu hình |
| `ArrayDeque` | Iterator thông thường đi từ đầu đến cuối deque |
| `HashMap` qua các view | Không bảo đảm thứ tự các entry/khóa/giá trị |
| `LinkedHashMap` qua các view | Thường là thứ tự thêm khóa; có thể được cấu hình theo truy cập |
| `TreeMap` qua các view thông thường | Theo thứ tự khóa, không theo giá trị |
| `PriorityQueue` qua `for-each` | Iterator không bảo đảm thứ tự ưu tiên |
| `Set.of`, `Set.copyOf` | Không bảo đảm thứ tự duyệt phần tử |

Các kiểu khung nhìn (view) đảo chiều hoặc iterator chuyên biệt có hợp đồng riêng. Bảng nói về cách duyệt thông thường của những nguồn được nêu, không thay thế việc đọc cấu hình và thao tác tạo view thực tế.

## 4. Mảng và list: thứ tự vị trí, không phải tự sắp xếp

Với dữ liệu `3, 1, 2`, duyệt mảng hoặc list giữ các vị trí đó. Kết quả không tự thành `1, 2, 3`.

List có thể chứa phần tử lặp lại. Ví dụ `List.of(3, 1, 2, 1)` vẫn gặp đủ bốn phần tử theo thứ tự đã tạo.

Nếu list đã được sắp xếp hoặc được xây theo một trình tự khác, `for-each` đi theo thứ tự hiện tại của nó. Vòng lặp không biết các phần tử ban đầu đến từ cơ sở dữ liệu, tập hợp băm hay một list khác.

Với `ArrayDeque`, thứ tự iterator là từ đầu đến cuối deque. Các thao tác thêm ở đầu hoặc cuối làm trình tự đó khác nhau. Đừng chỉ dựa vào thứ tự gọi phương thức mà bỏ qua việc phương thức thêm phần tử vào vị trí nào.

## 5. `HashSet`: không suy ra thứ tự từ một lần in thử

[HashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html) không bảo đảm thứ tự duyệt, kể cả việc thứ tự duy trì không đổi theo thời gian.

Một ví dụ số nguyên nhỏ có thể tình cờ xuất hiện như đã sắp tăng dần. Điều đó không khiến `HashSet` trở thành cấu trúc sắp xếp. Các chi tiết như dữ liệu, mã băm, dung lượng hoặc triển khai có thể ảnh hưởng thứ tự quan sát được, và chúng không phải hợp đồng thứ tự mà ứng dụng nên tự suy diễn.

Nếu yêu cầu nghiệp vụ chỉ là kiểm tra một phần tử có thuộc tập hợp không, thứ tự có thể không cần thiết. Nếu yêu cầu là xuất báo cáo hoặc tạo kết quả có thứ tự xác định, hãy chủ động xây thứ tự phù hợp.

```java
Set<Integer> values = new HashSet<>(List.of(3, 1, 2));
List<Integer> ordered = new ArrayList<>(values);
ordered.sort(Comparator.naturalOrder());
for (Integer value : ordered) {
    System.out.println(value);
}
```

Đầu ra `1`, `2`, `3` lúc này đến từ thao tác `sort`, không phải từ một lời hứa của `HashSet`. Các đoạn rời trong bài cần import kiểu thư viện tương ứng khi đặt vào một lớp Java.

Sao chép một `HashSet` sang `ArrayList` rồi không sắp xếp chỉ ghi nhận thứ tự gặp ở lượt sao chép đó. Sao chép sang `LinkedHashSet` cũng không khôi phục được lịch sử thêm phần tử đã không được nguồn giữ lại.

## 6. `LinkedHashSet`: giữ trình tự nhưng phải biết thao tác được dùng

Với các thao tác `add` thông thường:

```java
Set<Integer> values = new LinkedHashSet<>();
values.add(3);
values.add(1);
values.add(2);
values.add(1);
```

Thứ tự gặp là `3, 1, 2`. Thêm lại phần tử đang có bằng `add` không chuyển nó tới cuối; set vẫn chỉ giữ một phần tử tương đương theo `equals`.

Java hiện đại còn có các thao tác định vị tường minh trên những cấu trúc có thứ tự. Chẳng hạn `LinkedHashSet.addFirst` hoặc `addLast` trên Java 21 trở lên có thể đổi vị trí phần tử. Vì vậy, “luôn là thứ tự thêm ban đầu bất kể thao tác” là một kết luận quá rộng.

Hãy dựa trên hợp đồng [LinkedHashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashSet.html) và những thao tác thực tế được dùng. Chương trình minh họa cuối bài chỉ sử dụng các API tương thích Java 17.

## 7. `TreeSet`: có thứ tự và có quy tắc tương đương theo so sánh

[TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html) duyệt theo thứ tự tự nhiên hoặc comparator được truyền vào khi tạo.

Với các số `3, 1, 2, 1`, một `TreeSet<Integer>` tự nhiên có thứ tự `1, 2, 3`.

Nhưng không nên dùng `TreeSet` chỉ để “sắp xếp một list” nếu phải giữ mọi phần tử. Set không giữ phần tử trùng; với `TreeSet`, hai giá trị được coi là tương đương khi phép so sánh cho kết quả `0`.

Ví dụ hai công việc khác mã nhưng cùng độ ưu tiên sẽ bị xem là tương đương nếu comparator chỉ so độ ưu tiên. Một công việc có thể không được thêm vào set dù `equals` của chúng khác nhau.

Nếu cần giữ đủ các bản ghi và phần tử lặp lại, tạo một `ArrayList` rồi gọi `sort`. Việc sắp xếp và việc loại trùng là hai yêu cầu riêng cần được chọn có chủ đích.

## 8. Map: thứ tự của view đến từ map, không tự theo giá trị

`Map` không trực tiếp là `Iterable`. Thường duyệt các view như `entrySet()`, `keySet()` hoặc `values()`.

- Với `HashMap`, không giả định một thứ tự.
- Với `LinkedHashMap` mặc định và thao tác `put` thông thường, thứ tự khóa theo lần thêm mới; cập nhật giá trị của khóa đang có không tự chuyển khóa đó tới cuối.
- Với `TreeMap`, thứ tự các entry theo khóa, bằng thứ tự tự nhiên hoặc comparator của khóa.

Ví dụ thêm các khóa `3`, `1`, `2` vào `LinkedHashMap` mặc định cho thứ tự gặp khóa `3, 1, 2`. Tạo `TreeMap` từ dữ liệu đó cho thứ tự khóa `1, 2, 3`; giá trị gắn với từng khóa được giữ theo entry, không được sắp riêng theo nội dung giá trị.

[TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html) xác định thứ tự theo khóa. Nếu muốn xếp các entry theo giá trị, cần một quy tắc khác, chẳng hạn đưa entry vào list rồi sắp xếp bằng comparator phù hợp.

### Cấu hình theo truy cập làm `LinkedHashMap` khác mặc định

Có thể tạo map theo thứ tự truy cập:

```java
LinkedHashMap<Integer, String> values = new LinkedHashMap<>(16, 0.75f, true);
values.put(3, "C");
values.put(1, "A");
values.put(2, "B");
values.get(3);
```

Sau lần `get(3)`, thứ tự khóa là `1, 2, 3`: khóa vừa được truy cập chuyển về phía mới truy cập nhất trong thứ tự gặp thông thường.

Chương trình minh họa thực hiện lần truy cập này **trước khi** duyệt lại. Không nên suy ra có thể tùy ý gọi các thao tác thay đổi thứ tự ngay trong vòng duyệt đang chạy.

[LinkedHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html) còn có các thao tác định vị tường minh ở Java hiện đại. Phải đọc cả cấu hình lẫn các thao tác đã thực hiện để hiểu thứ tự hiện tại.

## 9. `PriorityQueue`: thứ tự lấy đầu hàng đợi khác thứ tự iterator

Một `PriorityQueue` có phần tử đầu là phần tử nhỏ nhất theo quan hệ thứ tự đã chọn. Nếu dùng comparator đảo, “nhỏ nhất theo comparator” có thể là số lớn nhất theo thứ tự số thông thường.

Nhưng [PriorityQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PriorityQueue.html) không bảo đảm iterator duyệt theo thứ tự ưu tiên.

Vì vậy, đoạn sau không phải cách xuất hàng đợi đã sắp xếp:

```java
for (Integer value : queue) {
    System.out.println(value);
}
```

Nếu cần lần lượt lấy theo ưu tiên, dùng `poll()` trên hàng đợi hoặc trên một bản sao:

```java
PriorityQueue<Integer> copy = new PriorityQueue<>(queue);
while (!copy.isEmpty()) {
    System.out.println(copy.poll());
}
```

Trong các đoạn trên, `queue` là một biến `PriorityQueue<Integer>` đã có. Bản sao kiểu `PriorityQueue` giữ quy tắc so sánh của nguồn; việc lấy phần tử làm rỗng bản sao, không làm rỗng hàng đợi gốc.

Nếu chỉ cần một list trình bày có thứ tự, có thể sao chép phần tử rồi sắp xếp theo comparator tương ứng. Khi có nhiều phần tử cùng ưu tiên, đừng tự giả định hàng đợi giữ thứ tự thêm giữa những phần tử hòa nhau; cần một tiêu chí phụ nếu thứ tự đó quan trọng.

## 10. Sắp xếp ổn định chưa đủ để tạo kết quả xác định từ nguồn không có thứ tự

`List.sort` là phép sắp xếp ổn định: những phần tử so sánh bằng `0` giữ thứ tự tương đối từ list đầu vào. Điều này hữu ích nhưng không tự tạo ra một thứ tự gốc mà nguồn không bảo đảm.

Ví dụ list chứa công việc `B`, `A`, `C`, với độ ưu tiên tương ứng `1`, `1`, `2`:

- Sắp theo độ ưu tiên giữ `B` trước `A` vì hai phần tử hòa nhau và thứ tự nguồn đã là `B, A`.
- Sắp theo độ ưu tiên rồi mã cho `A, B, C`.

Nếu list được sao chép từ một nguồn không cam kết thứ tự, chỉ so độ ưu tiên có thể giữ lại một thứ tự hòa nhau không được nghiệp vụ xác định. Muốn đầu ra xác định, cần đủ tiêu chí so sánh để giải quyết những trường hợp cần phân biệt.

```java
Comparator<Task> order = Comparator.comparingInt(Task::priority)
                                   .thenComparing(Task::id);
```

`Task` được khai báo trong chương trình dưới đây. Tính ổn định của [List.sort](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)) và độ đầy đủ của comparator là hai điều khác nhau.

Các tập hợp không cho sửa như `Set.of` cũng không tự có thứ tự thêm đáng dựa vào. Hợp đồng [Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#unmodifiable) nêu thứ tự duyệt của các tập hợp đó không được quy định.

## 11. Chương trình hoàn chỉnh

Lưu vào `EncounterOrderDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.TreeMap;
import java.util.TreeSet;

public class EncounterOrderDemo {
    record Task(String id, int priority) {
        @Override
        public String toString() { return id; }
    }

    public static void main(String[] args) {
        int[] array = {3, 1, 2};
        List<Integer> arrayOrder = new ArrayList<>();
        for (int value : array) {
            arrayOrder.add(value);
        }
        System.out.println("array = " + arrayOrder);

        List<Integer> input = List.of(3, 1, 2, 1);
        System.out.println("list = " + input);
        System.out.println("linked set = " + new LinkedHashSet<>(input));
        System.out.println("tree set = " + new TreeSet<>(input));

        HashSet<Integer> hashSet = new HashSet<>(input);
        List<Integer> sortedHashCopy = new ArrayList<>();
        for (Integer value : hashSet) {
            sortedHashCopy.add(value);
        }
        sortedHashCopy.sort(Comparator.naturalOrder());
        System.out.println("hash set sorted copy = " + sortedHashCopy);

        ArrayDeque<Integer> deque = new ArrayDeque<>(List.of(3, 1, 2));
        deque.addFirst(9);
        System.out.println("deque head to tail = " + new ArrayList<>(deque));

        Map<Integer, String> insertionMap = new LinkedHashMap<>();
        insertionMap.put(3, "C");
        insertionMap.put(1, "A");
        insertionMap.put(2, "B");
        System.out.println("linked map keys = " + new ArrayList<>(insertionMap.keySet()));
        System.out.println("tree map keys = " + new ArrayList<>(new TreeMap<>(insertionMap).keySet()));

        LinkedHashMap<Integer, String> accessMap = new LinkedHashMap<>(16, 0.75f, true);
        accessMap.putAll(insertionMap);
        System.out.println("access map before get = " + new ArrayList<>(accessMap.keySet()));
        accessMap.get(3);
        System.out.println("access map after get = " + new ArrayList<>(accessMap.keySet()));

        PriorityQueue<Integer> queue = new PriorityQueue<>(List.of(5, 1, 4, 2, 3));
        List<Integer> queueMembers = new ArrayList<>();
        for (Integer value : queue) {
            queueMembers.add(value);
        }
        queueMembers.sort(Comparator.naturalOrder());
        System.out.println("queue members sorted copy = " + queueMembers);
        List<Integer> polled = new ArrayList<>();
        while (!queue.isEmpty()) {
            polled.add(queue.poll());
        }
        System.out.println("queue poll order = " + polled);

        List<Task> tasks = List.of(new Task("B", 1), new Task("A", 1), new Task("C", 2));
        Comparator<Task> priorityOnly = Comparator.comparingInt(Task::priority);
        List<Task> stable = new ArrayList<>(tasks);
        stable.sort(priorityOnly);
        System.out.println("stable priority sort = " + stable);
        stable.sort(priorityOnly.thenComparing(Task::id));
        System.out.println("priority then id = " + stable);

        TreeSet<Task> priorities = new TreeSet<>(priorityOnly);
        priorities.addAll(tasks);
        System.out.println("tree set with priority comparator size = " + priorities.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 EncounterOrderDemo.java
java EncounterOrderDemo
```

Kết quả chuẩn:

```text
array = [3, 1, 2]
list = [3, 1, 2, 1]
linked set = [3, 1, 2]
tree set = [1, 2, 3]
hash set sorted copy = [1, 2, 3]
deque head to tail = [9, 3, 1, 2]
linked map keys = [3, 1, 2]
tree map keys = [1, 2, 3]
access map before get = [3, 1, 2]
access map after get = [1, 2, 3]
queue members sorted copy = [1, 2, 3, 4, 5]
queue poll order = [1, 2, 3, 4, 5]
stable priority sort = [B, A, C]
priority then id = [A, B, C]
tree set with priority comparator size = 2
```

Chương trình cố ý không đưa thứ tự iterator thô của `HashSet` hoặc `PriorityQueue` vào đầu ra cần khớp. Với hai cấu trúc này, list phần tử được sắp tường minh trước khi in; thứ tự `poll` của queue được kiểm tra riêng.

Hai công việc `B` và `A` cùng độ ưu tiên khiến `TreeSet` dùng comparator chỉ theo độ ưu tiên giữ hai mức ưu tiên, không giữ đủ ba công việc. Đây là hệ quả của quy tắc tương đương theo comparator, không phải lỗi của `for-each`.

## 12. Chọn cấu trúc theo yêu cầu thứ tự

- Cần giữ vị trí và phần tử lặp: dùng list; sắp xếp tường minh nếu cần.
- Cần loại trùng và giữ thứ tự thêm thông thường: cân nhắc `LinkedHashSet`.
- Cần tập hợp luôn theo comparator và chấp nhận quy tắc tương đương của nó: cân nhắc `TreeSet`.
- Cần lưu khóa/giá trị theo thứ tự thêm hoặc truy cập: chọn cấu hình `LinkedHashMap` phù hợp.
- Cần map theo thứ tự khóa: cân nhắc `TreeMap`.
- Cần lấy phần tử kế tiếp theo ưu tiên: dùng `PriorityQueue.poll()`, không coi iterator của queue là một danh sách đã sắp xếp.
- Chỉ cần kiểm tra thành viên/tra cứu và không có yêu cầu thứ tự: không thêm giả định thứ tự vào hợp đồng của cấu trúc băm.

Khi thứ tự là một phần của API, hãy ghi rõ cho người dùng. Chỉ khai báo `Set<T>` hoặc `Collection<T>` không tự nói hết những cam kết về thứ tự mà một triển khai cụ thể có thể cung cấp.

## 13. Tự kiểm tra

**Câu 1.** Một `HashSet<Integer>` in `1, 2, 3` nhiều lần có chứng minh nó sắp tăng dần không?

Không. Đó là kết quả quan sát, không phải hợp đồng thứ tự của `HashSet`.

**Câu 2.** Vì sao `for-each` qua `PriorityQueue` không thay thế vòng `poll()`?

Iterator không bảo đảm thứ tự ưu tiên, còn `poll()` lấy phần tử đầu theo quy tắc ưu tiên và loại nó khỏi hàng đợi.

**Câu 3.** `TreeMap` sắp các entry theo khóa hay theo giá trị?

Theo khóa và comparator của khóa. Muốn theo giá trị cần một thao tác sắp xếp khác.

**Câu 4.** Sắp list ổn định theo độ ưu tiên có luôn cho thứ tự mã công việc giống nhau không?

Không. Phần tử hòa nhau giữ thứ tự đầu vào. Cần tiêu chí phụ nếu yêu cầu có một thứ tự mã xác định.

**Câu 5.** Sao chép `HashSet` sang `LinkedHashSet` có tìm lại được thứ tự thêm ban đầu không?

Không. Nó giữ thứ tự gặp trong lúc sao chép, không khôi phục lịch sử mà nguồn không cung cấp.
