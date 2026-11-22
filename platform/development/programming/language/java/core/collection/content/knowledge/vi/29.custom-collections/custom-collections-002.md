# AbstractCollection, AbstractList, AbstractSequentialList và AbstractSet

## 1. Vì sao một collection tùy chỉnh cần lớp khung?

Giả sử bạn có dữ liệu được lưu theo cách riêng: một vùng mảng, một chuỗi nút liên kết, hoặc một bộ dữ liệu chỉ cho phép đọc. Bạn muốn người dùng của lớp vẫn gọi được những thao tác quen thuộc như `contains`, `toArray`, `iterator` hoặc `addAll`.

Nếu viết `implements Collection<E>` từ đầu, bạn phải tự cung cấp nhiều hành vi vốn có thể suy ra từ những thao tác nền tảng. Ví dụ, khi đã biết cách duyệt phần tử, bạn có thể tìm một phần tử bằng cách duyệt; khi đã biết cách thêm một phần tử, bạn có thể thêm cả nhóm bằng cách lặp lại thao tác ấy.

Các lớp `AbstractCollection`, `AbstractList`, `AbstractSequentialList` và `AbstractSet` cung cấp **cài đặt khung**: phần thuật toán có thể tái sử dụng được viết sẵn, còn lớp con cung cấp những thao tác gắn với dữ liệu và các ràng buộc của mình.

Hãy phân biệt ba tầng:

- **Giao diện** như `Collection`, `List`, `Set` mô tả hợp đồng mà phía sử dụng nhìn thấy.
- **Lớp khung** tổ chức việc thực hiện nhiều phương thức từ một số thao tác nền tảng.
- **Lớp cụ thể** quyết định lưu dữ liệu ở đâu, cho phép sửa những gì và giữ các bất biến nào.

Lớp khung không tự tạo một kho lưu phần tử cho bạn. Kế thừa `AbstractList` không tự có mảng; kế thừa `AbstractSet` không tự có bảng băm và cũng không tự lọc phần tử trùng trong dữ liệu của lớp con.

Quan hệ giữa bốn lớp:

```text
AbstractCollection<E> implements Collection<E>
├── AbstractList<E> implements List<E>
│   └── AbstractSequentialList<E>
└── AbstractSet<E> implements Set<E>
```

Đây đều là lớp trừu tượng. Muốn có đối tượng, bạn cần một lớp con cụ thể hoàn thiện những phương thức còn thiếu; lớp con ấy có thể được đặt tên hoặc được khai báo ẩn danh. Trong các ví dụ, ta đặt tên để nhìn rõ trách nhiệm và đường gọi.

**Điểm cần học không phải số lượng phương thức phải viết.** Bạn cần biết phương thức kế thừa sẽ gọi trở lại đâu, điều gì xảy ra nếu thao tác nền tảng không được hỗ trợ, và độ phức tạp có phù hợp với cách lưu dữ liệu hay không.

Lộ trình của bài là: chọn lớp khung → đọc sự phụ thuộc giữa phương thức → viết một lớp cụ thể nhỏ → kiểm chứng thao tác kế thừa → rà soát ràng buộc và chi phí.

## 2. Chọn lớp khung từ ngữ nghĩa và cách truy cập

| Lớp khung | Ngữ nghĩa cần cung cấp | Điểm xuất phát để đọc dữ liệu | Muốn sửa đầy đủ cần chú ý |
| --- | --- | --- | --- |
| `AbstractCollection<E>` | Một nhóm phần tử, chưa khẳng định là danh sách hay tập hợp | `iterator()`, `size()` | Thêm qua `add(E)`; xóa qua bộ duyệt có `remove()`. |
| `AbstractList<E>` | Danh sách có vị trí và thứ tự | `get(int)`, `size()` | Thay bằng `set(int,E)`; đổi kích thước bằng `add(int,E)`, `remove(int)`. |
| `AbstractSequentialList<E>` | Danh sách mà đi theo con trỏ là cách truy cập tự nhiên | `listIterator(int)`, `size()` | Bộ duyệt phải có các thao tác `set`, `add`, `remove` tương ứng với khả năng sửa. |
| `AbstractSet<E>` | Tập hợp không có phần tử trùng theo hợp đồng `Set` | `iterator()`, `size()` | Tự giữ tính duy nhất trên mọi đường đưa dữ liệu vào; thêm/xóa tương tự nền `AbstractCollection`. |

Bảng này mô tả hướng xây dựng thông dụng, không bắt buộc mọi collection đều phải hỗ trợ tất cả thao tác sửa. Một danh sách có thể chỉ đọc; một danh sách khác có thể cho phép thay phần tử nhưng không thêm/xóa.

Nguồn hợp đồng của bốn lớp là [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html), [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html), [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html) và [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html) trong Java 17.

Hai tiêu chí cần được tách riêng:

1. **Ngữ nghĩa:** người dùng cần danh sách có vị trí, tập hợp không trùng, hay chỉ một nhóm phần tử?
2. **Cơ chế dữ liệu:** truy cập phần tử theo chỉ số có rẻ không, hay giữ một con trỏ để đi tiếp mới rẻ?

Không chọn `AbstractSet` chỉ vì muốn ít phương thức; việc đã khai báo là `Set` kéo theo nghĩa vụ không trùng và quy tắc bằng nhau của tập hợp. Không chọn `AbstractList` chỉ vì lớp dữ liệu có thể miễn cưỡng cung cấp `get(i)` bằng cách đi lại từ đầu mỗi lần.

### 2.1. Phương thức tùy chọn không có nghĩa là có thể bỏ qua khi thiết kế

Trong Collections Framework, một số thao tác sửa là tùy chọn: một cài đặt có thể không hỗ trợ và ném `UnsupportedOperationException`. Lớp khung thường dùng chính cách này làm hành vi mặc định cho những thao tác sửa chưa được lớp con cung cấp.

Ví dụ, `AbstractCollection.add(E)` không tự tìm một chỗ lưu để thêm. Nếu lớp con không ghi đè, lời gọi thêm sẽ không được hỗ trợ. Nhưng `contains()` có thể hoạt động ngay khi lớp con có bộ duyệt đúng.

Một thao tác có tên liên quan đến sửa cũng không nhất thiết luôn ném ngoại lệ trên mọi đầu vào. Với một cài đặt kế thừa cách duyệt để xóa, `remove("khong-co")` có thể trả `false` mà chưa cần đến thao tác xóa của bộ duyệt. Khi tìm thấy một phần tử cần xóa, nó mới gặp thao tác không được hỗ trợ.

Vì vậy, đừng dùng kết quả của một lần gọi không làm thay đổi dữ liệu để kết luận lớp hỗ trợ sửa. Phải xác định hợp đồng và kiểm tra trường hợp thật sự cần thay đổi. [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) là nguồn tra cứu cho khái niệm thao tác tùy chọn và các hạn chế phần tử.

### 2.2. Kế thừa không thay thế việc giữ bất biến

Một vài bất biến phải do lớp cụ thể duy trì:

- Số lượng trả về phù hợp với dữ liệu và cách duyệt trong điều kiện sử dụng được hỗ trợ.
- Chỉ số hợp lệ được xử lý đúng, chỉ số ngoài miền báo lỗi thích hợp.
- Bộ duyệt tiến lên và kết thúc đúng, không trả một giá trị giả để báo hết.
- Nếu là `Set`, không có phần tử trùng theo quy tắc bằng nhau đã chọn.
- Nếu công bố chỉ đọc, không để lộ một đường sửa qua bộ duyệt hoặc đối tượng lưu nền.
- Nếu dùng `modCount` cho danh sách, các thay đổi cấu trúc được ghi nhận đúng.

Một lớp biên dịch được mới chỉ hoàn thành yêu cầu kiểu. Các bất biến này quyết định nó có thực hiện đúng hợp đồng collection hay không.

## 3. AbstractCollection: tái sử dụng từ cách duyệt

### 3.1. Những đường gọi quan trọng

Với `AbstractCollection`, hãy bắt đầu bằng `iterator()` và `size()`. Các thao tác kế thừa có thể dùng chúng:

```text
isEmpty()              → size()
contains(x)            → iterator() và kiểm tra phần tử
remove(x)              → tìm bằng iterator(), rồi iterator.remove()
addAll(source)         → duyệt source, gọi add(e)
removeAll / retainAll  → duyệt và dùng iterator.remove() khi cần
clear()                → duyệt rồi xóa từng phần tử
toArray() / toString() → dựa vào việc duyệt dữ liệu
```

Đây là bản đồ phụ thuộc giúp đọc ví dụ, không phải cam kết rằng mọi lớp con phải giữ nguyên các thuật toán ấy. Nếu kho lưu có cách tìm/xóa nhanh hơn, lớp con có thể ghi đè phương thức phù hợp mà vẫn giữ hợp đồng.

`removeIf` có một điểm về nơi khai báo: đây là phương thức mặc định của `Collection`, không phải một phương thức do `AbstractCollection` tự khai báo. Cài đặt mặc định duyệt rồi dùng `Iterator.remove()` cho phần tử thỏa điều kiện. Nguồn chi tiết là [Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

Như vậy, chỉ hỗ trợ `add(E)` chưa làm một collection trở thành có thể xóa. Chỉ viết `remove(Object)` riêng cũng chưa tự làm `retainAll` kế thừa hoạt động nếu bộ duyệt vẫn không thể xóa. Cần đọc đúng đường gọi của phương thức mà bạn định công bố.

### 3.2. Chương trình: một nhóm cho sửa và một nhóm chỉ đọc

Ví dụ sau dùng `ArrayList` làm nơi lưu để tập trung vào cài đặt khung. `Bag` chấp nhận phần tử trùng và `null`; nó không khai báo mình là `List` hay `Set`. `ReadOnlyBag` sao chép đầu vào rồi chỉ trả bộ duyệt không thể sửa.

Lưu thành `AbstractCollectionDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class AbstractCollectionDemo {
    public static void main(String[] args) {
        Bag<String> bag = new Bag<>(Arrays.asList("red", "red", null, "blue"));
        System.out.println("initial = " + bag);
        System.out.println("remove one red = " + bag.remove("red"));
        System.out.println("after remove = " + bag);
        bag.removeIf(Objects::isNull);
        bag.addAll(List.of("blue", "green"));
        System.out.println("after removeIf and addAll = " + bag);
        bag.retainAll(Set.of("blue"));
        System.out.println("after retainAll = " + bag);
        bag.clear();
        System.out.println("after clear = " + bag);

        ReadOnlyBag<String> readOnly = new ReadOnlyBag<>(List.of("A", "B"));
        System.out.println("read-only contains A = " + readOnly.contains("A"));
        expectUnsupported("read-only add", () -> readOnly.add("C"));
        System.out.println("read-only remove missing = " + readOnly.remove("Z"));
        expectUnsupported("read-only remove present", () -> readOnly.remove("A"));
        System.out.println("same contents equal = "
                + readOnly.equals(new ReadOnlyBag<>(List.of("A", "B"))));
    }

    private static final class Bag<E> extends AbstractCollection<E> {
        private final List<E> data;

        private Bag() {
            data = new ArrayList<>();
        }

        private Bag(Collection<? extends E> source) {
            data = new ArrayList<>(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E element) {
            return data.add(element);
        }
    }

    private static final class ReadOnlyBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        private ReadOnlyBag() {
            this(List.of());
        }

        private ReadOnlyBag(Collection<? extends E> source) {
            data = Collections.unmodifiableList(new ArrayList<>(source));
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    private static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractCollectionDemo.java
java AbstractCollectionDemo
```

Kết quả:

```text
initial = [red, red, null, blue]
remove one red = true
after remove = [red, null, blue]
after removeIf and addAll = [red, blue, blue, green]
after retainAll = [blue, blue]
after clear = []
read-only contains A = true
read-only add -> UnsupportedOperationException
read-only remove missing = false
read-only remove present -> UnsupportedOperationException
same contents equal = false
```

### 3.3. Đọc kết quả theo thao tác nền tảng

`Bag` chỉ viết ba phương thức làm việc với phần tử: `iterator`, `size` và `add`. Những biến đổi còn lại trong `main` đến từ hành vi kế thừa:

- `remove("red")` chỉ xóa một lần xuất hiện, nên vẫn còn một `red`.
- `removeIf` xóa phần tử `null` bằng bộ duyệt có hỗ trợ xóa.
- `addAll` dùng `add` để thêm từng mục, nên `blue` được giữ cả hai lần.
- `retainAll` không biến nhóm thành tập hợp; nó giữ cả hai lần xuất hiện của `blue`.
- `clear` xóa hết thông qua bộ duyệt.

`ReadOnlyBag` không ghi đè `add`, nên lời gọi thêm bị từ chối. Với `remove("Z")`, thuật toán không tìm thấy mục cần xóa và trả `false`. Với `remove("A")`, nó tìm thấy mục nhưng bộ duyệt không hỗ trợ xóa, nên ném ngoại lệ. Hai kết quả này cùng phù hợp với cài đặt đã chọn.

Hai `ReadOnlyBag` có cùng dữ liệu vẫn cho `equals` bằng `false`. `AbstractCollection` không tự thêm quy tắc so sánh theo nội dung; lớp ví dụ dùng hành vi của `Object`. Không được suy ra từ hình thức in `[A, B]` rằng mọi collection đều có nghĩa bằng nhau giống danh sách.

Bản sao trong `ReadOnlyBag` là bản sao cấu trúc. Nếu phần tử là một đối tượng có thể thay đổi, mã bên ngoài vẫn có thể thay đổi chính đối tượng ấy qua một tham chiếu khác. Không cho sửa cấu trúc collection khác với làm toàn bộ đồ thị đối tượng trở nên bất biến.

Các lớp con được đặt `private` và `final` trong một chương trình minh họa; chúng chưa phải một thư viện công khai. Với lớp tổng quát dùng lại, thiết kế thêm mức truy cập, tài liệu về phần tử được phép, và các hàm tạo thích hợp. Hàm tạo không đối số và hàm tạo nhận `Collection<? extends E>` là một quy ước hữu ích, không phải phương thức do giao diện bắt buộc.


## 4. AbstractList: dùng thao tác theo chỉ số làm nền

### 4.1. Hướng xây dựng của danh sách truy cập trực tiếp

Với kho dữ liệu kiểu mảng, thao tác `get(i)` tự nhiên và rẻ. `AbstractList` tận dụng điều đó: bạn cung cấp thao tác theo chỉ số, lớp khung xây bộ duyệt và nhiều hành vi danh sách dựa trên chúng.

Đường gọi cần nhớ:

```text
get(i), size()                 → nền đọc
iterator(), listIterator(...)  → dùng các thao tác theo chỉ số
add(e)                         → add(size(), e)
iterator.remove()              → remove(index) của danh sách
listIterator.set(e)            → set(index, e)
listIterator.add(e)            → add(index, e)
clear()                        → removeRange(0, size())
```

Hai phương thức đọc `get(int)` và `size()` đủ để bắt đầu một danh sách không cho sửa. Để thay phần tử, cung cấp `set(int,E)`. Để thay đổi kích thước đầy đủ, cung cấp thêm `add(int,E)` và `remove(int)`. Bộ duyệt kế thừa dựa vào chính những thao tác ấy. Xem [AbstractList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

Một lỗi rất dễ mắc là chỉ ghi đè `add(E)`. Khi đó một số thao tác thêm cuối có thể hoạt động, nhưng `add(index,E)` và thao tác thêm qua `ListIterator` vẫn có thể không được hỗ trợ. Với hướng xây dựng của lớp khung này, thao tác thêm theo vị trí mới là nền thích hợp để triển khai.

Cũng cần phân biệt chữ ký:

- `remove(int index)` xóa theo vị trí và trả phần tử cũ.
- `remove(Object value)` xóa một lần xuất hiện theo giá trị và trả `boolean`.

Đây là hai thao tác khác nhau. Với danh sách số nguyên, chọn nhầm chữ ký có thể xóa nhầm vị trí, dù lớp cụ thể đã cài đặt hoàn toàn đúng.

### 4.2. Miền chỉ số của phần tử khác miền vị trí con trỏ

Với danh sách có `n` phần tử:

| Thao tác | Miền hợp lệ |
| --- | --- |
| `get(i)`, `set(i,e)`, `remove(i)` | `0 <= i < n` |
| `add(i,e)` | `0 <= i <= n` |
| `listIterator(i)` | `0 <= i <= n` |
| `subList(from,to)` | `0 <= from <= to <= n`; đầu `from` được lấy, đầu `to` bị loại |

Vị trí `n` không chứa phần tử để đọc, nhưng là chỗ hợp lệ để chèn cuối hoặc đặt con trỏ ở cuối. Đừng dùng cùng một phép kiểm tra cho tất cả phương thức.

Phương thức `set` trả phần tử cũ và giữ nguyên kích thước. `add` chèn, làm các phần tử phía sau dịch chỉ số. `remove(int)` xóa và dịch phần còn lại về trước. Lớp khung không tự sửa các lỗi lệch một vị trí trong phần lưu trữ của lớp con.

### 4.3. Chương trình: danh sách nhỏ lưu trên mảng

`ArrayBuffer` dưới đây tự lưu dữ liệu trong `Object[]`. Nó không dùng `ArrayList` làm nơi lưu, nên bạn nhìn thấy rõ phần việc mà lớp con phải thực hiện: kiểm tra chỉ số, mở rộng mảng, dịch phần tử, cập nhật số lượng và ghi nhận thay đổi cấu trúc.

Lưu thành `AbstractListDemo.java`:

```java
import java.util.AbstractList;
import java.util.Arrays;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class AbstractListDemo {
    public static void main(String[] args) {
        ArrayBuffer<String> list = new ArrayBuffer<>();
        list.addAll(List.of("A", "B", "C"));
        System.out.println("initial = " + list);

        ListIterator<String> cursor = list.listIterator(1);
        System.out.println("cursor next = " + cursor.next());
        cursor.set("B*");
        cursor.add("X");
        System.out.println("after cursor add = " + list);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.remove();
        System.out.println("after cursor remove = " + list);

        List<String> middle = list.subList(1, 3);
        middle.set(0, "B2");
        middle.remove(1);
        System.out.println("backing after view edits = " + list);
        System.out.println("equals standard list = " + list.equals(List.of("A", "B2")));
        System.out.println("same list hash = "
                + (list.hashCode() == List.of("A", "B2").hashCode()));

        Iterator<String> afterSet = list.iterator();
        list.set(0, "A2");
        System.out.println("iterator after set = " + afterSet.next());

        Iterator<String> stale = list.iterator();
        list.add("D");
        try {
            stale.next();
            throw new AssertionError("structural change was not detected");
        } catch (ConcurrentModificationException ex) {
            System.out.println("stale iterator -> " + ex.getClass().getSimpleName());
        }
        list.subList(1, list.size()).clear();
        System.out.println("after range clear = " + list);
    }

    private static final class ArrayBuffer<E>
            extends AbstractList<E> implements RandomAccess {
        private Object[] elements = new Object[2];
        private int count;

        @Override
        public int size() {
            return count;
        }

        @Override
        @SuppressWarnings("unchecked")
        public E get(int index) {
            Objects.checkIndex(index, count);
            return (E) elements[index];
        }

        @Override
        public E set(int index, E element) {
            E previous = get(index);
            elements[index] = element;
            return previous;
        }

        @Override
        public void add(int index, E element) {
            if (index < 0 || index > count) {
                throw new IndexOutOfBoundsException("index: " + index);
            }
            if (count == elements.length) {
                int capacity = Math.addExact(count, Math.max(1, count / 2));
                elements = Arrays.copyOf(elements, capacity);
            }
            System.arraycopy(elements, index, elements, index + 1, count - index);
            elements[index] = element;
            count++;
            modCount++;
        }

        @Override
        public E remove(int index) {
            E previous = get(index);
            System.arraycopy(elements, index + 1, elements, index, count - index - 1);
            elements[--count] = null;
            modCount++;
            return previous;
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractListDemo.java
java AbstractListDemo
```

Kết quả:

```text
initial = [A, B, C]
cursor next = B
after cursor add = [A, B*, X, C]
cursor previous = X
after cursor remove = [A, B*, C]
backing after view edits = [A, B2]
equals standard list = true
same list hash = true
iterator after set = A2
stale iterator -> ConcurrentModificationException
after range clear = [A2]
```

### 4.4. Vì sao chỉ năm phương thức mà bộ duyệt sửa được danh sách?

Lớp cụ thể cung cấp `get`, `size`, `set`, `add(int,E)` và `remove(int)`. Nó không tự viết `iterator()` hay `listIterator()`.

Bộ duyệt danh sách được tạo ở vị trí 1, trước `B`. Sau `next()`, phần tử vừa trả là `B`. `set("B*")` thay nó. `add("X")` chèn trước phần tử mà lần `next()` tiếp theo sẽ trả, nên danh sách thành `[A, B*, X, C]`. Con trỏ đã ở sau `X`, vì vậy `previous()` trả `X`, rồi `remove()` xóa chính mục vừa được trả đó.

Các phương thức kế thừa đã thực hiện việc quản lý con trỏ và gọi đúng thao tác của lớp con. Nhưng tính đúng của mảng vẫn phụ thuộc lớp con:

- Khi chèn, dịch đoạn từ `index` sang phải trước khi ghi phần tử mới.
- Khi xóa, dịch phần phía sau sang trái.
- Sau khi xóa, đặt ô thừa cuối mảng về `null` để không giữ lại một tham chiếu không còn thuộc danh sách.
- Tăng `count` hoặc giảm `count` đúng một lần.
- Chỉ trả về giá trị tại chỉ số đã được xác thực.

Phép ép từ `Object` về `E` ở `get` được giới hạn trong một phương thức và có `@SuppressWarnings("unchecked")`. Cơ sở của nó là mảng chỉ được ghi qua những đường nhận `E` của lớp, không được công khai cho mã ngoài. Đây không phải lý do để tắt cảnh báo cho cả dự án hoặc dùng kiểu thô.

Mảng được tăng dung lượng khi đầy; `Math.addExact` tránh cho phép tính dung lượng âm thầm tràn. Mã vẫn là ví dụ học tập nhỏ, chưa có toàn bộ chính sách dung lượng tối đa và tối ưu hóa của một collection dùng trong thư viện. Nó không hứa có thể cấp phát mảng lớn tùy ý.

### 4.5. modCount ghi nhận thay đổi cấu trúc

`AbstractList` có trường `protected modCount`. Bộ duyệt kế thừa có thể dùng nó để phát hiện một thay đổi cấu trúc không đi qua bộ duyệt đang dùng.

Trong `ArrayBuffer`:

- `add(int,E)` thành công làm thay đổi kích thước, nên tăng `modCount` một lần.
- `remove(int)` thành công cũng tăng một lần.
- `set(int,E)` chỉ thay giá trị tại một vị trí, nên không tăng.
- Một yêu cầu bị từ chối do chỉ số sai không được sửa dữ liệu hay tăng bộ đếm.

[Hợp đồng modCount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount) lưu ý không tăng hơn một lần trong một lời gọi đơn `add(int,E)` hoặc `remove(int)` khi dùng cơ chế bộ duyệt có sẵn. Tăng ở cả phương thức ngoài lẫn hàm trợ giúp bên trong có thể khiến bộ duyệt nhận nhầm rằng đã có một sửa đổi ngoài ý muốn.

Không đồng nhất `modCount` với kích thước: xóa một mục rồi thêm một mục có thể giữ nguyên kích thước cuối cùng nhưng đã thay đổi cấu trúc hai lần. Bộ duyệt tạo trước hai thao tác ấy không thể coi dữ liệu như chưa đổi.

Chương trình minh họa hai trường hợp trong **một luồng**:

1. Tạo bộ duyệt, dùng `set` thay `A` bằng `A2`, rồi gọi `next()`. Nó đọc `A2` bình thường.
2. Tạo bộ duyệt khác, thêm `D` trực tiếp vào danh sách, rồi gọi `next()`. Bộ duyệt kế thừa phát hiện thay đổi và ném `ConcurrentModificationException`.

Ngoại lệ này không chứng minh có hai luồng. Nó báo một kiểu sử dụng không phù hợp với bộ duyệt. Cũng không được dùng khả năng báo lỗi ấy làm cơ chế đồng bộ hóa: [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) mô tả hành vi phát hiện lỗi là cố gắng tốt nhất, không phải bảo đảm an toàn khi nhiều luồng sửa không đồng bộ.

`modCount` không tự khóa dữ liệu, không tự làm một nhóm thao tác trở nên nguyên tử và không tạo một bản chụp cho bộ duyệt.

### 4.6. subList là một khung nhìn có liên hệ với danh sách gốc

`middle = list.subList(1,3)` không sao chép `B*` và `C` sang một danh sách độc lập. `middle.set(0,"B2")` thay phần tử ở vị trí tương ứng trong danh sách gốc. `middle.remove(1)` xóa `C` khỏi danh sách gốc. Vì vậy kết quả là `[A, B2]`.

Các sửa đổi đi qua khung nhìn được ánh xạ về danh sách nền; thông tin kích thước và thay đổi cấu trúc phải được theo dõi nhất quán. Khi lớp con tự quản lý lưu trữ, một `modCount` bị bỏ sót có thể gây lỗi cả ở khung nhìn, không chỉ ở bộ duyệt đơn.

Sau khi thay đổi cấu trúc trực tiếp trên danh sách gốc ngoài khung nhìn, đừng tiếp tục dựa vào khung nhìn cũ. Theo hợp đồng [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)), ngữ nghĩa của khung nhìn trở nên không xác định khi nền bị sửa cấu trúc theo cách không đi qua nó. Một triển khai có thể phát hiện và ném ngoại lệ, nhưng ngoại lệ không phải cách “làm mới” khung nhìn.

Chương trình không dùng lại `middle` sau khi thêm `D` ở danh sách gốc. Nó tạo một khung nhìn mới để xóa đoạn cuối.

### 4.7. Tái sử dụng đúng chưa chắc đã tối ưu

`get(i)` của `ArrayBuffer` là truy cập mảng sau kiểm tra chỉ số, nên phù hợp với hướng `AbstractList`. Việc triển khai `RandomAccess` cũng phù hợp với đặc điểm này. [RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) là giao diện đánh dấu để thuật toán tổng quát nhận biết kiểu truy cập nhanh; kế thừa `AbstractList` không tự có dấu ấy và cũng không làm `get` nhanh hơn.

Ngược lại, việc chèn/xóa giữa mảng cần dịch dữ liệu. Bộ duyệt kế thừa có thể dùng đúng thao tác nhưng vẫn phải trả chi phí ấy.

`clear()` kế thừa gọi `removeRange(0,size())`. Cài đặt nền của `removeRange` dùng bộ duyệt để xóa từng phần tử. Với mảng, xóa lặp từ đầu có thể dịch dữ liệu nhiều lần và đạt chi phí bậc hai. Một bước tối ưu thích hợp là ghi đè `removeRange` để dịch đoạn còn lại một lần, xóa các ô thừa, cập nhật số lượng và `modCount` đúng.

Không cần viết lại mọi phương thức ngay từ đầu. Trước hết giữ một cài đặt đúng và hiểu đường gọi; sau đó chọn điểm ghi đè giúp cải thiện tình huống sử dụng thật. `removeRange` là một điểm như vậy vì cả `clear` của danh sách lẫn thao tác xóa qua `subList` có thể hưởng lợi.


## 5. AbstractSequentialList: đảo hướng phụ thuộc sang ListIterator

### 5.1. Có get(int) không đồng nghĩa với truy cập trực tiếp rẻ

Một danh sách liên kết vẫn có thể cung cấp `get(i)`. Nhưng để tìm vị trí ấy, nó cần di chuyển qua các nút. Nếu mỗi lần lấy phần tử lại bắt đầu một lượt tìm vị trí, vòng lặp theo chỉ số có thể đi qua dữ liệu nhiều lần.

Hướng tự nhiên hơn là đặt con trỏ một lần rồi gọi `next()` để đi tiếp. `AbstractSequentialList` chọn hướng ấy: lớp con cung cấp `listIterator(int)` và `size()`; các thao tác theo chỉ số được xây trên bộ duyệt.

```text
get(i)      → listIterator(i).next()
set(i,e)    → đặt bộ duyệt ở i, next(), rồi set(e)
add(i,e)    → đặt bộ duyệt ở i, rồi add(e)
remove(i)   → đặt bộ duyệt ở i, next(), rồi remove()
iterator()  → dùng bộ duyệt danh sách
```

So với `AbstractList`, hướng phụ thuộc đã đảo lại. Hai lớp đều thực hiện `List` nhưng khác điểm tựa của thuật toán. Đây là khác biệt thiết kế cốt lõi được mô tả trong [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html).

Một lỗi khi chọn lớp này là viết `listIterator(i)` bằng cách gọi lại `get(i)` kế thừa. `get(i)` vốn đang gọi `listIterator(i)`, nên bạn tạo vòng gọi đệ quy thay vì một nền truy cập dữ liệu. Phương thức nền phải đi đến nơi lưu thật hoặc một bộ duyệt nền độc lập.

### 5.2. Bộ duyệt phải có hợp đồng đầy đủ

`ListIterator` có con trỏ nằm **giữa** các phần tử. Danh sách có `n` mục có `n+1` vị trí con trỏ, từ trước mục đầu đến sau mục cuối.

Các phương thức đọc cần được cài đặt nhất quán: `hasNext`, `next`, `hasPrevious`, `previous`, `nextIndex`, `previousIndex`. Khi hết hướng tương ứng, `next` hoặc `previous` phải ném `NoSuchElementException`, không trả `null` để báo hết vì `null` có thể là một phần tử hợp lệ.

Các phương thức sửa `remove`, `set`, `add` phải được triển khai hoặc từ chối rõ ràng bằng `UnsupportedOperationException`. Không có một phương thức chung tên `index()` thay thế hai phương thức chỉ số của `ListIterator`.

Với bộ duyệt có hỗ trợ sửa:

- `set` và `remove` tác động lên phần tử vừa được `next` hoặc `previous` trả về.
- `add` chèn tại vị trí con trỏ và đặt con trỏ sau phần tử mới.
- Không được gọi `remove` liên tiếp hai lần cho cùng một lần trả phần tử.
- Sau `add`, không thể dùng ngay `set` hoặc `remove` như thể phần tử mới được trả bởi `next`/`previous`.

Nguồn quy tắc trạng thái là [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html). Lớp khung sẽ dựa vào những điều này để thực hiện thao tác khác; một bộ duyệt “gần đúng” có thể làm nhiều phương thức kế thừa sai theo.

### 5.3. Chương trình: một lớp tuần tự ủy quyền bộ duyệt

Ví dụ dùng `LinkedList` làm cấu trúc lưu nền, rồi bọc bộ duyệt của nó. Mục đích là nhìn thấy hướng tái sử dụng của `AbstractSequentialList`, không viết lại toàn bộ thuật toán nút liên kết.

Phần bọc có hai công việc riêng:

1. Đếm số lần bắt đầu bộ duyệt để quan sát đường gọi.
2. Cập nhật `modCount` của lớp ngoài khi thêm/xóa thành công, để khung nhìn kế thừa theo dõi được thay đổi cấu trúc.

Lưu thành `AbstractSequentialListDemo.java`:

```java
import java.util.AbstractSequentialList;
import java.util.Collection;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class AbstractSequentialListDemo {
    public static void main(String[] args) {
        SequentialBuffer<String> list = new SequentialBuffer<>(List.of("A", "B", "C"));
        list.iteratorStarts = 0;
        StringBuilder indexed = new StringBuilder();
        for (int i = 0; i < list.size(); i++) {
            indexed.append(list.get(i));
        }
        int indexedStarts = list.iteratorStarts;

        list.iteratorStarts = 0;
        StringBuilder traversed = new StringBuilder();
        for (String value : list) {
            traversed.append(value);
        }
        int traversalStarts = list.iteratorStarts;
        System.out.println("indexed values = " + indexed);
        System.out.println("indexed iterator starts = " + indexedStarts);
        System.out.println("traversal values = " + traversed);
        System.out.println("traversal iterator starts = " + traversalStarts);

        ListIterator<String> cursor = list.listIterator(1);
        System.out.println("cursor next = " + cursor.next());
        cursor.set("B*");
        cursor.add("X");
        System.out.println("after cursor add = " + list);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.remove();
        System.out.println("after cursor remove = " + list);
        list.subList(1, 3).clear();
        System.out.println("after view clear = " + list);
        try {
            list.get(list.size());
            throw new AssertionError("end position is not an element");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get at end -> " + ex.getClass().getSimpleName());
        }
    }

    private static final class SequentialBuffer<E>
            extends AbstractSequentialList<E> {
        private final LinkedList<E> data;
        private int iteratorStarts;

        private SequentialBuffer() {
            data = new LinkedList<>();
        }

        private SequentialBuffer(Collection<? extends E> source) {
            data = new LinkedList<>(source);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public ListIterator<E> listIterator(int index) {
            ListIterator<E> delegate = data.listIterator(index);
            iteratorStarts++;
            return new ListIterator<>() {
                @Override
                public boolean hasNext() {
                    return delegate.hasNext();
                }

                @Override
                public E next() {
                    return delegate.next();
                }

                @Override
                public boolean hasPrevious() {
                    return delegate.hasPrevious();
                }

                @Override
                public E previous() {
                    return delegate.previous();
                }

                @Override
                public int nextIndex() {
                    return delegate.nextIndex();
                }

                @Override
                public int previousIndex() {
                    return delegate.previousIndex();
                }

                @Override
                public void remove() {
                    delegate.remove();
                    modCount++;
                }

                @Override
                public void set(E element) {
                    delegate.set(element);
                }

                @Override
                public void add(E element) {
                    delegate.add(element);
                    modCount++;
                }
            };
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractSequentialListDemo.java
java AbstractSequentialListDemo
```

Kết quả:

```text
indexed values = ABC
indexed iterator starts = 3
traversal values = ABC
traversal iterator starts = 1
cursor next = B
after cursor add = [A, B*, X, C]
cursor previous = X
after cursor remove = [A, B*, C]
after view clear = [A]
get at end -> IndexOutOfBoundsException
```

### 5.4. Ba lần bắt đầu khác một lần đi tiếp

Trong vòng lặp theo chỉ số, mỗi `get(i)` kế thừa tạo một bộ duyệt ở `i` rồi lấy phần tử kế tiếp. Với ba mục, bộ đếm ghi nhận ba lần bắt đầu.

Trong `for-each`, `iterator()` cung cấp một bộ duyệt, rồi vòng lặp dùng tiếp nó. Bộ đếm chỉ là 1. Hai cách đều cho chuỗi `ABC`, nhưng đường đi qua tầng truy cập không giống nhau.

Đây là phép quan sát số lần gọi trong chính ví dụ. Nó không đo nano giây, không chứng minh một máy cụ thể nhanh hơn bao nhiêu và không suy ra chi phí cho mọi cài đặt `AbstractSequentialList`.

Với dữ liệu liên kết, chi phí định vị mới là lý do phải quan tâm. [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) mô tả việc truy cập theo chỉ số bằng cách đi từ đầu hoặc cuối gần hơn. Lặp lại việc định vị cho từng chỉ số có thể cho tổng chi phí bậc hai; giữ một bộ duyệt rồi đi tiếp thường tránh phần lặp lại đó.

Nếu bạn dùng `AbstractList` cho một kho liên kết mà chỉ cung cấp `get(i)` bằng cách đi từ đầu, bộ duyệt kế thừa dựa trên `get` cũng có thể kéo theo chi phí xấu. Tên giao diện `List` không quyết định tốc độ; cần xem cách các phương thức gọi nhau và cách kho lưu thực hiện việc tìm vị trí.

### 5.5. Vì sao không trả trực tiếp bộ duyệt LinkedList rồi bỏ qua phần bọc?

Bộ duyệt của `LinkedList` theo dõi thay đổi trong chính `LinkedList`. Nhưng lớp ngoài cũng kế thừa các cơ chế của `AbstractList`, chẳng hạn khung nhìn `subList` dựa vào trạng thái thay đổi cấu trúc của danh sách ngoài.

Nếu lớp ngoài thay đổi nền mà không cập nhật `modCount` của mình, hai tầng có thể nhìn thấy các phiên bản cấu trúc khác nhau. Ở ví dụ, mỗi `delegate.add` hoặc `delegate.remove` thành công được theo sau bởi đúng một lần tăng bộ đếm ngoài. `delegate.set` không đổi kích thước nên không tăng.

Nếu thao tác của `delegate` ném ngoại lệ, câu lệnh tăng sau đó không chạy. Điều này tránh ghi nhận một sửa đổi chưa xảy ra. Các trạng thái hợp lệ của bộ duyệt, phép kiểm tra biên và phát hiện sửa đổi trên nền được ủy quyền cho bộ duyệt `LinkedList`.

Đây là một thiết kế cụ thể sử dụng hai tầng đối tượng. Nếu tự viết cấu trúc nút và bộ duyệt, bạn phải tự quản lý con trỏ, phần tử vừa trả, số lượng và cơ chế phát hiện sửa đổi. Không có một yêu cầu rằng mọi lớp con của `AbstractSequentialList` đều phải bọc `LinkedList`.

Lần `subList(1,3).clear()` xóa được `B*` và `C` thông qua các đường gọi đã thiết kế. `get(list.size())` sau đó ném `IndexOutOfBoundsException`: vị trí cuối là chỗ đặt con trỏ hợp lệ, nhưng không phải phần tử hợp lệ để đọc. `AbstractSequentialList` chuyển tình huống hết phần tử khi đọc theo chỉ số thành ngoại lệ chỉ số phù hợp.

### 5.6. Khi nào nên chọn hướng này?

Chọn `AbstractSequentialList` khi thao tác đi tiếp/lùi qua vị trí hiện tại là nền truy cập tốt, còn truy cập ngẫu nhiên phải định vị. Bạn không cần cố tạo một `get` trông giống mảng để rồi xây mọi thao tác khác trên nó.

Ngược lại, với kho mảng có `get(i)` rẻ, `AbstractList` thường giúp biểu diễn trực tiếp hơn. Việc `AbstractSequentialList` là lớp con của `AbstractList` không làm nó “đầy đủ hơn” cho mọi tình huống. Nó chuyên biệt hóa hướng xây dựng cho một kiểu truy cập khác.

Trong cả hai hướng, các thao tác sửa có thể bị giới hạn theo thiết kế: chỉ đọc, cho thay nhưng cố định kích thước, hoặc cho thêm/xóa. Hợp đồng công khai phải phản ánh đúng các khả năng ấy; không suy ra từ chữ “sequential” rằng danh sách được phép sửa hay an toàn cho nhiều luồng.


## 6. AbstractSet: có khung hợp đồng, vẫn phải tự giữ tính duy nhất

### 6.1. Không có bảng băm được tạo ngầm

`AbstractSet` kế thừa nền duyệt của `AbstractCollection` và thực hiện giao diện `Set`. Lớp con vẫn cần cung cấp `iterator` và `size`. Nếu muốn thêm phần tử, cần cung cấp `add` thích hợp.

Điều được bổ sung ở đây là ngữ nghĩa tập hợp, đặc biệt các cài đặt `equals` và `hashCode` phù hợp với `Set`. Ngoài ra, `AbstractSet` còn có cài đặt `removeAll` riêng. Nó không phải `HashSet` rút gọn: không có yêu cầu rằng dữ liệu phải được lưu bằng băm và không có thuật toán chống trùng tự động chặn mọi lần ghi vào kho riêng của lớp con.

Nếu lớp con dùng một mảng hoặc danh sách nền, rồi `add` chỉ nối phần tử vào cuối, các phần tử bằng nhau vẫn có thể xuất hiện nhiều lần. Kế thừa tên lớp không sửa được bất biến bị vi phạm đó.

Với ví dụ nhỏ, cách giữ tính duy nhất là kiểm tra có phần tử bằng nhau trước khi thêm. Nếu đã có, trả `false` và không thay đổi. Nếu chưa có, lưu phần tử rồi trả `true`. Khi chọn một thuật toán tốt hơn, bạn vẫn phải giữ ý nghĩa của kết quả và quan hệ bằng nhau.

Các ràng buộc này thuộc [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html); phần tái sử dụng cụ thể thuộc [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

### 6.2. Chương trình: tập hợp nhỏ lưu bằng danh sách

`TinySet` cố ý dùng `ArrayList` để bạn thấy rõ rằng một `Set` không nhất thiết được lưu bằng bảng băm. Nó chấp nhận một `null`, duyệt theo thứ tự thêm trong cài đặt này và tìm bằng cách duyệt.

Lưu thành `AbstractSetDemo.java`:

```java
import java.util.AbstractSet;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

public class AbstractSetDemo {
    public static void main(String[] args) {
        TinySet<String> set = new TinySet<>();
        System.out.println("add alpha = " + set.add("alpha"));
        System.out.println("add equal alpha = " + set.add(new String("alpha")));
        set.add("beta");
        set.add(null);
        System.out.println("initial = " + set);

        Set<String> other = new HashSet<>(Arrays.asList(null, "beta", "alpha"));
        System.out.println("equals standard set = " + set.equals(other));
        System.out.println("reverse equality = " + other.equals(set));
        System.out.println("same set hash = " + (set.hashCode() == other.hashCode()));
        System.out.println("equals list = " + set.equals(Arrays.asList("alpha", "beta", null)));
        set.removeAll(Collections.singleton("alpha"));
        System.out.println("after removeAll = " + set);

        Iterator<String> cursor = set.iterator();
        System.out.println("iterator next = " + cursor.next());
        cursor.remove();
        System.out.println("after iterator remove = " + set);

        TinySet<String> copied = new TinySet<>(Arrays.asList("x", "x", null));
        System.out.println("copy = " + copied);
        System.out.println("copy size = " + copied.size());
        System.out.println("add second null = " + copied.add(null));
    }

    private static final class TinySet<E> extends AbstractSet<E> {
        private final List<E> data = new ArrayList<>();

        private TinySet() {
        }

        private TinySet(Collection<? extends E> source) {
            addAll(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E element) {
            if (contains(element)) {
                return false;
            }
            return data.add(element);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractSetDemo.java
java AbstractSetDemo
```

Kết quả:

```text
add alpha = true
add equal alpha = false
initial = [alpha, beta, null]
equals standard set = true
reverse equality = true
same set hash = true
equals list = false
after removeAll = [beta, null]
iterator next = beta
after iterator remove = [null]
copy = [x, null]
copy size = 2
add second null = false
```

### 6.3. Không trùng phải đúng trên mọi đường đưa dữ liệu vào

Lần `add("alpha")` thay đổi tập hợp nên trả `true`. Lần thêm `new String("alpha")` có một đối tượng khác nhưng nội dung bằng nhau; nó trả `false`. Việc tạo `String` mới chỉ phục vụ kiểm chứng bằng nhau theo giá trị, không phải một cách viết chuỗi nên áp dụng thường ngày.

Hàm tạo nhận `Collection` không sao chép thẳng mọi mục vào `data`. Nó gọi `addAll(source)`, mà đường kế thừa thêm từng phần tử qua `add` đã kiểm tra trùng. Vì vậy đầu vào `["x", "x", null]` tạo tập hợp có hai mục `[x, null]`.

Nếu thay bằng `data.addAll(source)`, ta có thể bỏ qua quy tắc chống trùng của lớp ngoài. Đây là lý do phải kiểm tra cả hàm tạo, phương thức hàng loạt và mọi đường cập nhật riêng, không chỉ một lần gọi `set.add(...)` ở phía người dùng.

`data` được giữ riêng và không trả trực tiếp cho mã sử dụng. Bộ duyệt cho phép xóa nhưng không có thao tác chèn, nên đường này không tạo thêm bản trùng. Chính sách cho `null` đến từ thiết kế `TinySet` và kho nền, không phải một cam kết rằng mọi lớp con của `AbstractSet` đều nhận `null`.

Thứ tự in trong ví dụ là đặc điểm của `TinySet` với nền `ArrayList`. Không lấy nó làm bảo đảm thứ tự cho mọi `Set`. Nghĩa bằng nhau của tập hợp vẫn không phụ thuộc thứ tự duyệt.

### 6.4. equals và hashCode của tập hợp khác danh sách

`set` và `other` trong chương trình có cùng các phần tử nhưng được xây theo thứ tự khác nhau và thuộc hai lớp khác nhau. Hai chiều `equals` đều là `true`; mã băm cũng bằng nhau. Điều này giúp các cài đặt tuân thủ `Set` làm việc với nhau.

Trong khi đó, một `List` chứa đúng các mục ấy vẫn không bằng `Set`. Không dùng phép so sánh “cùng các mục” tùy ý để xóa bỏ ranh giới ngữ nghĩa giữa danh sách và tập hợp.

So sánh ba hướng:

| Nền lớp | Ý nghĩa bằng nhau kế thừa | Thứ tự có ảnh hưởng không? |
| --- | --- | --- |
| `AbstractCollection` | Không tự thêm quy tắc nội dung; nếu lớp con không đổi thì theo `Object` | Không có một quy tắc so sánh nội dung chung được áp đặt tại đây. |
| `AbstractList` và `AbstractSequentialList` | Bằng một `List` khác khi cùng độ dài và từng cặp phần tử tương ứng bằng nhau | Có. |
| `AbstractSet` | Bằng một `Set` khác khi cùng các phần tử và cùng số lượng | Không. |

Mã băm của danh sách tích lũy theo thứ tự với hệ số 31; mã băm của tập hợp là tổng mã băm các phần tử, với `null` đóng góp 0. Không đổi một công thức thành công thức kia chỉ vì dữ liệu lưu nền giống nhau.

Nếu tự định nghĩa so sánh theo nội dung cho một nhóm không phải `List` hoặc `Set`, cần giữ tính đối xứng và quy tắc mã băm. Không thể cho nhóm ấy tự nhận bằng một danh sách trong khi danh sách lại từ chối bằng nhóm ấy. Trong ví dụ `Bag`, giữ hành vi `Object` tránh tự đặt thêm một quy tắc ngoài mục tiêu minh họa.

Tính duy nhất cũng phụ thuộc quan hệ bằng nhau của phần tử. Nếu thay đổi các trường dùng trong `equals` khi đối tượng còn trong tập hợp, bạn có thể làm những phần tử trước đó khác nhau trở nên bằng nhau. Chọn phần tử có giá trị ổn định hoặc xác định một chính sách cập nhật rõ ràng; lớp khung không theo dõi mọi sửa đổi bên trong đối tượng.

### 6.5. removeAll có thể đi theo hai đường khác nhau

`AbstractSet.removeAll` xem xét kích thước của hai collection để chọn một trong các hướng:

- Duyệt đối số rồi gọi `remove(Object)` của tập hợp nhận.
- Hoặc duyệt tập hợp nhận, kiểm tra đối số có chứa mục hay không, rồi xóa bằng bộ duyệt của tập hợp nhận.

Chi tiết được thể hiện trong [AbstractSet.removeAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html#removeAll(java.util.Collection)) và [mã OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractSet.java).

Vì vậy, nếu chỉ viết một `remove(Object)` riêng nhưng bộ duyệt không cho xóa, bạn chưa thể kết luận mọi đầu vào của `removeAll` sẽ hoạt động. Đường được chọn còn phụ thuộc dữ liệu. Muốn công bố hỗ trợ thao tác ấy, cần bảo đảm các phụ thuộc phù hợp hoặc ghi đè nó bằng một cài đặt đúng.

`TinySet` trả bộ duyệt của danh sách nền có hỗ trợ xóa, nên các đường sửa đang dùng đều có nền tương ứng. Sau `removeAll` xóa `alpha`, bộ duyệt lấy `beta` rồi xóa nó, để lại `null`.

Đây cũng là ví dụ vì sao không nên đoán thuật toán chỉ từ tên phương thức. Cùng một thao tác giao diện có thể được lớp khung chuyên biệt hóa để phù hợp hơn với loại collection.

### 6.6. Tính đúng của Set không kéo theo chi phí của HashSet

Trong `TinySet`, `contains` kế thừa duyệt các phần tử. Thêm một mục mới cần kiểm tra trùng, nên chi phí tăng theo số mục hiện có. Thêm hàng loạt nhiều mục khác nhau có thể có tổng chi phí bậc hai.

Mã băm của tập hợp cần duyệt phần tử. So sánh hai tập hợp còn phụ thuộc chi phí tìm trong phía được hỏi; không được mặc định mọi `Set` đều có tra cứu thời gian hằng số.

Một cấu trúc nhỏ dựa trên danh sách có thể thích hợp để học hoặc phục vụ một miền dữ liệu rất nhỏ. Nếu yêu cầu chính là tra cứu lớn, hãy chọn một cấu trúc lưu phù hợp. Kế thừa `AbstractSet` tái sử dụng hợp đồng và thuật toán nền, không tự chọn cấu trúc dữ liệu thay bạn.

## 7. Rà soát một cài đặt tùy chỉnh trước khi công bố

### 7.1. Kiểm tra cả phương thức kế thừa

Đừng chỉ thử `add` rồi `get`. Hãy thử những đường mà người dùng có thể gọi gián tiếp:

- Với `AbstractCollection`: `contains`, `remove(Object)`, `addAll`, `retainAll`, `removeIf`, `clear` và chuyển sang mảng.
- Với danh sách: bộ duyệt thường, `ListIterator`, thêm ở đầu/cuối, biên chỉ số, `subList` và xóa một đoạn.
- Với tập hợp: thêm đối tượng bằng nhau nhưng khác tham chiếu, hàm tạo nhận đầu vào có trùng, `addAll`, so sánh với một cài đặt `Set` chuẩn và mã băm.
- Với kiểu chỉ đọc: thử cả thao tác thực sự cần đổi dữ liệu; không chỉ thử các trường hợp không làm gì.

Các phương thức hàng loạt mặc định thường thực hiện từng bước. Nếu một bước ném ngoại lệ, đừng tự suy ra mọi thay đổi trước đó đã được hoàn tác. Nếu bài toán cần kiểm tra toàn bộ đầu vào trước khi sửa, hoặc cần bảo đảm nguyên tử giữa các luồng, phải thiết kế riêng yêu cầu ấy.

Bốn lớp khung không tự cung cấp một chính sách an toàn cho truy cập đồng thời. Dùng bộ đếm thay đổi hay bắt `ConcurrentModificationException` không thay thế việc đồng bộ hóa.

### 7.2. Chọn kế thừa khi cần công bố đúng hợp đồng

Nếu mục tiêu là làm một `List` hoặc `Set` tùy chỉnh để tham gia vào các thuật toán của Collections Framework, lớp khung có giá trị vì tái sử dụng đúng ngữ nghĩa.

Nếu mục tiêu chỉ là giữ một danh sách riêng bên trong một đối tượng nghiệp vụ, bạn có thể dùng một collection có sẵn bằng cách chứa nó trong lớp và chỉ công bố các thao tác cần thiết. Không cần biến mọi lớp có nhiều phần tử thành một collection kế thừa.

Ví dụ trong bài cố ý cho thấy cả hai cơ chế cùng xuất hiện: lớp cụ thể kế thừa lớp khung, còn việc lưu trữ có thể dùng một đối tượng nền. Nhưng khi thiết kế API thật, phải quyết định bạn muốn công bố toàn bộ hợp đồng collection hay chỉ một nhóm hành vi nghiệp vụ hẹp hơn.

### 7.3. Ghi đè để tối ưu nhưng giữ hợp đồng

Một điểm ghi đè tốt có thể giúp nhiều thao tác kế thừa cùng nhanh hơn: `contains` cho một kho có chỉ mục phù hợp, `removeRange` cho mảng, hoặc `addAll` khi có thể sao chép một đoạn hiệu quả.

Mỗi tối ưu phải giữ các điều kiện quan sát được: kết quả trả về, thứ tự với danh sách, không trùng với tập hợp, xử lý chỉ số và phần tử không hợp lệ, chính sách sửa, bộ duyệt và khung nhìn. “Chạy nhanh hơn” không bù được việc một đường thêm lách qua kiểm tra trùng hay một thay đổi cấu trúc không được ghi nhận.

Khi phân tích hiệu năng, lần theo cả chuỗi gọi. Một phương thức kế thừa có vẻ ngắn vẫn có thể gọi lặp một thao tác tuyến tính. Ngược lại, việc cùng thực hiện giao diện `List` không buộc hai cấu trúc phải có cùng chi phí.

## 8. Thực hành và tự kiểm tra có lời giải

### Bài 1. Chỉ đọc với AbstractCollection

Bạn viết đúng `iterator()` và `size()`, không ghi đè `add`. Bộ duyệt không hỗ trợ xóa. `contains(x)`, `add(x)`, `remove(x)` sẽ ra sao?

**Lời giải:** `contains` có thể hoạt động dựa trên việc duyệt. `add` mặc định ném `UnsupportedOperationException`. `remove` có thể trả `false` khi không tìm thấy mục; nếu tìm thấy và cần gọi thao tác xóa không được hỗ trợ của bộ duyệt, nó ném ngoại lệ. Không suy luận khả năng sửa từ một lần xóa mục vắng mặt.

**Thực hành:** với `ReadOnlyBag` ở chương trình đầu, thử một `removeIf` không khớp mục nào và một điều kiện khớp `A`. Giải thích khác biệt theo đường gọi `Iterator.remove`, không theo tên phương thức.

### Bài 2. Danh sách cố định kích thước

Một lớp con của `AbstractList` cung cấp `get`, `size`, `set`, nhưng giữ nguyên hành vi mặc định của `add(int,E)` và `remove(int)`. Có thể thay phần tử qua `ListIterator` không? Có thể thêm qua bộ duyệt không?

**Lời giải:** có thể thay khi trạng thái bộ duyệt cho phép `set`, vì nó gọi `set` của lớp con. Không thể thêm qua bộ duyệt vì thao tác nền `add(int,E)` chưa được hỗ trợ. Khả năng thay giá trị không đồng nghĩa với khả năng đổi kích thước.

**Thực hành:** tạo một danh sách cố định từ bản sao một mảng, triển khai ba phương thức đọc/thay nói trên. Kiểm tra kích thước giữ nguyên và các chỉ số biên được xử lý đúng.

### Bài 3. Hai lần tăng modCount trong một lần thêm

`add(int,E)` gọi hàm trợ giúp; cả hai nơi đều tăng `modCount`. Vì sao bộ duyệt có thể báo lỗi dù bạn chỉ gọi `listIterator.add(e)`?

**Lời giải:** bộ duyệt kế thừa có cơ chế theo dõi số lần thay đổi cấu trúc mong đợi. Một thao tác đơn bị đếm hai lần có thể làm cơ chế này nhận nhầm sự chênh lệch. Chọn một nơi duy nhất ghi nhận lần thêm thành công. Không tăng chỉ vì gọi một hàm trợ giúp hoặc vì yêu cầu thêm đã được gửi tới.

**Thực hành:** đọc đường gọi của `ArrayBuffer.add` và xác định dòng nào thực sự hoàn tất cập nhật cấu trúc. Giải thích vì sao `set` không tăng bộ đếm trong cài đặt này.

### Bài 4. Dữ liệu liên kết nhưng dùng bộ duyệt dựa trên get

Bạn kế thừa `AbstractList` và viết `get(i)` bằng cách đi từ nút đầu đến vị trí `i`. `for-each` có chắc là tuyến tính không?

**Lời giải:** không. Bộ duyệt kế thừa có thể gọi `get` theo từng chỉ số. Tổng số bước đi qua nút có thể là `1 + 2 + ... + n`, tức bậc hai. Chọn nền `AbstractSequentialList` với bộ duyệt đi tiếp hiệu quả, hoặc tự cung cấp bộ duyệt phù hợp và rà soát các đường còn lại.

**Thực hành:** ở chương trình tuần tự, tăng số phần tử rồi quan sát số lần bắt đầu bộ duyệt. Phân biệt số lần gọi đã đo được với số nút phải đi qua và thời gian chạy thực tế.

### Bài 5. Set chống trùng trong add nhưng không chống trong hàm tạo

Một lớp con `AbstractSet` kiểm tra trùng trong `add`, nhưng hàm tạo dùng thẳng `new ArrayList<>(source)`. Nếu `source` có hai mục bằng nhau, lớp đã đúng hợp đồng chưa?

**Lời giải:** chưa. Dữ liệu được tạo ra đã vi phạm tính duy nhất trước khi ai gọi `add` trên đối tượng mới. Cần đưa đầu vào qua một đường giữ bất biến, hoặc tự lọc đúng trong quá trình dựng. `TinySet` dùng `addAll` đi qua `add`.

**Thực hành:** thử đầu vào có cùng tham chiếu lặp lại, hai đối tượng khác tham chiếu nhưng bằng nhau, và nhiều `null` nếu chính sách cho phép. Kiểm tra cả kích thước lẫn nội dung.

### Bài 6. Dùng cùng công thức mã băm cho List và Set

Bạn muốn dùng tổng mã băm phần tử cho mọi collection để tái sử dụng thêm. Có giữ đúng hợp đồng danh sách không?

**Lời giải:** không thể thay tùy ý công thức chuẩn của `List`. Danh sách có so sánh theo thứ tự và công thức mã băm tương ứng; tập hợp có so sánh không phụ thuộc thứ tự và công thức riêng. Hai danh sách bằng nhau phải tương thích mã băm với những cài đặt `List` khác, không chỉ với lớp tự viết.

**Thực hành:** so sánh một danh sách tùy chỉnh với `List.of("A","B")` ở cả hai chiều, rồi kiểm tra mã băm. Làm tương tự với `TinySet` và `HashSet`, cố ý đổi thứ tự thêm.

### Bài 7. Chỉ viết remove(Object) cho tập hợp

Bộ duyệt không hỗ trợ xóa, nhưng `remove(Object)` đã được ghi đè và hoạt động. Có thể công bố rằng `removeAll` kế thừa luôn được hỗ trợ không?

**Lời giải:** chưa đủ. `AbstractSet.removeAll` có thể chọn đường xóa qua bộ duyệt tùy kích thước. Phải hỗ trợ các thao tác nền mà thuật toán có thể dùng hoặc ghi đè `removeAll` phù hợp với khả năng đã công bố.

**Thực hành:** thiết kế hai đầu vào làm tập hợp nhận lớn hơn và nhỏ hơn đối số. Theo dõi đường nào được chọn trong mã nguồn đang dùng; không chỉ kiểm tra một kích thước rồi suy ra mọi trường hợp.

## 9. Kiểm chứng và tài liệu đối chiếu

Bốn chương trình trong bài được biên dịch với `javac --release 17 -encoding UTF-8 -Xlint:all`, chạy trên OpenJDK 24.0.2 và cho đúng các khối đầu ra đã nêu. Mức `--release 17` kiểm tra cú pháp/API theo Java 17 lúc biên dịch; nó không có nghĩa lần chạy kiểm chứng đã dùng JVM 17.

Các quan sát như số lần bắt đầu bộ duyệt, thứ tự in của `TinySet` và việc tăng `modCount` thuộc đúng các lớp ví dụ đã viết. Những đường tái sử dụng được đối chiếu với hợp đồng Java 17; khi lớp con ghi đè thuật toán, cần phân tích lại cài đặt thực tế ấy.

Nguồn chính để tra cứu:

- [AbstractCollection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html): nền duyệt, thêm/xóa tùy chọn và thuật toán kế thừa.
- [AbstractList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): thao tác theo chỉ số, bộ duyệt, `modCount`, `removeRange` và khung nhìn.
- [AbstractSequentialList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html): cách xây thao tác theo chỉ số từ bộ duyệt danh sách.
- [AbstractSet — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html): ràng buộc tập hợp, so sánh, mã băm và `removeAll`.
- [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): hợp đồng phải giữ dù chọn cách lưu nào.
- [ListIterator — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html): con trỏ, trạng thái sửa và ngoại lệ.
- [Mã AbstractList trong OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java) và [mã AbstractSet](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractSet.java): đối chiếu chi tiết đường gọi của cài đặt nền; không thay thế hợp đồng của mọi lớp con.
