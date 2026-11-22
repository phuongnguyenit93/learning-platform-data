# Viết Iterator, hỗ trợ remove và xử lý trạng thái con trỏ

## Iterator là một lượt duyệt có trạng thái

Một collection chứa dữ liệu; một `Iterator<E>` mô tả một lượt đi qua dữ liệu ấy. Iterator không chỉ là hàm “lấy phần tử ở chỉ số i”. Nó còn phải nhớ đã đi đến đâu và phần tử nào đang đủ điều kiện để xóa.

Giả sử collection có các phần tử:

~~~text
[A, B, C, D]
~~~

Sau khi iterator trả `B`, có hai thông tin khác nhau:

- Lần `next()` tiếp theo cần trả `C`.
- Lần `remove()` hợp lệ tiếp theo cần xóa `B`.

Nếu dùng một biến không có ý nghĩa rõ ràng cho cả hai, việc xóa dễ làm con trỏ nhảy quá `C`, xóa nhầm `C` hoặc cho phép xóa lại `B` lần thứ hai.

Bài học tập trung vào một iterator đi tới trên kho mảng, rồi liên hệ với iterator trên nút liên kết và `ListIterator` hai chiều. Ví dụ đầy đủ tự quản lý mảng, thao tác dồn phần tử và trạng thái xóa để có thể nhìn thấy nguyên nhân của từng bước cập nhật.

Ba thuật ngữ sẽ dùng:

| Thuật ngữ | Ý nghĩa trong ví dụ |
| --- | --- |
| `cursor` | Chỉ số phần tử sẽ được `next()` trả ở lần thành công tiếp theo |
| `lastReturned` | Chỉ số phần tử được `next()` trả gần nhất và chưa bị iterator này xóa |
| `expectedModCount` | Số phiên bản cấu trúc mà iterator đang mong đợi |

Tên biến chỉ là lựa chọn của ví dụ. Điều cần giữ là ý nghĩa và bất biến của chúng.

## Hợp đồng cần đáp ứng trước khi viết mã

`Iterator` có hai phương thức đọc nền tảng:

- `hasNext()` cho biết còn phần tử để đọc tiếp.
- `next()` trả phần tử tiếp theo; nếu đã hết thì ném `NoSuchElementException`.

`remove()` là thao tác tùy chọn: nếu hỗ trợ, nó xóa phần tử được iterator trả gần nhất, chỉ một lần cho mỗi lần `next()` thành công. Phần cài đặt mặc định của `Iterator.remove` ném `UnsupportedOperationException`. Các điều kiện này được quy định trong [Iterator của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Điều đó dẫn tới vài yêu cầu quan trọng:

1. Gọi `next` không bắt buộc phải gọi `hasNext` trước.
2. Gọi `hasNext` nhiều lần không được tự làm mất phần tử chưa trả.
3. `null` có thể là một phần tử hợp lệ nếu collection cho phép; không dùng nó để báo hết dữ liệu.
4. Một iterator hỗ trợ xóa phải từ chối `remove` trước lần đọc hợp lệ đầu tiên.
5. Sau khi xóa thành công, phải có một lần đọc thành công mới trước khi xóa tiếp.
6. `hasNext` trả `false` không tự hủy quyền xóa phần tử cuối vừa được trả.

Điểm cuối dễ nhầm. “Không còn phần tử phía trước” khác “không còn phần tử vừa trả để xóa”. Một iterator có thể vừa trả phần tử cuối, kiểm tra đã hết, rồi xóa chính phần tử cuối ấy.

### Phân biệt ba loại lỗi

| Tình huống | Ngoại lệ phù hợp |
| --- | --- |
| Không hỗ trợ xóa qua iterator | `UnsupportedOperationException` |
| Có hỗ trợ xóa, nhưng chưa có phần tử vừa trả hợp lệ hoặc đã xóa nó | `IllegalStateException` |
| `next` được gọi khi hết dữ liệu | `NoSuchElementException` |

Nếu triển khai chọn chính sách phát hiện thay đổi cấu trúc từ bên ngoài, nó còn có thể ném `ConcurrentModificationException` tại các điểm đã quy định.

Khi một lời gọi đồng thời vi phạm nhiều điều kiện, không nên dựa vào một thứ tự kiểm tra ngoại lệ chung cho mọi triển khai. Ví dụ phía dưới chủ động kiểm tra trạng thái `remove` trước, rồi mới kiểm tra thay đổi cấu trúc. Các phép thử dùng từng điều kiện riêng để kết quả có ý nghĩa rõ ràng.

## Thiết kế trạng thái cho iterator trên mảng

Giả sử mảng hoạt động được dùng ở đoạn `[0, size)`. Các ô từ `size` trở đi là vùng không có phần tử của collection.

Khi chưa có thay đổi ngoài giao thức và iterator còn hợp lệ, giữ các bất biến:

~~~text
0 <= cursor <= size

lastReturned == -1
    hoặc là chỉ số phần tử được next trả gần nhất, chưa bị remove

lastReturned hợp lệ sau next:
    lastReturned == cursor - 1
~~~

Khởi tạo:

~~~text
cursor = 0
lastReturned = -1
expectedModCount = modCount của collection lúc tạo iterator
~~~

`-1` là tín hiệu “chưa có đích xóa hợp lệ”. Không dùng `null` cho ý nghĩa ấy, vì dữ liệu có thể chứa `null`.

### hasNext chỉ quan sát

Trong thiết kế đơn giản này:

~~~java
@Override
public boolean hasNext() {
    return cursor < size;
}
~~~

Nó không tăng `cursor`, không đặt `lastReturned`, không đọc rồi bỏ phần tử.

Nếu gọi hai lần `hasNext` trước `next`, phần tử tiếp theo vẫn phải là phần tử ban đầu. Nếu `hasNext` làm tăng chỉ số, vòng lặp thường dùng dưới đây sẽ bỏ qua dữ liệu:

~~~java
while (iterator.hasNext()) {
    E value = iterator.next();
    use(value);
}
~~~

Đoạn trên chỉ minh họa cách sử dụng; `use` là hành động của ứng dụng.

Trong ví dụ, `hasNext` không kiểm tra phiên bản cấu trúc. Điều này là lựa chọn cụ thể, không phải bảo đảm rằng sau mọi thay đổi bên ngoài `hasNext` vẫn có ý nghĩa. Các lời gọi kiểm tra phiên bản nằm ở `next` và `remove` hợp lệ.

### next phải tự kiểm tra đã hết

Một lần `next` thành công làm ba việc:

1. Kiểm tra iterator chưa bị vô hiệu hóa bởi thay đổi cấu trúc bên ngoài.
2. Kiểm tra `cursor < size`.
3. Đọc phần tử tại `cursor`, nhớ vị trí vừa trả rồi tăng `cursor`.

Dạng cốt lõi:

~~~java
E value = elementAt(cursor);
lastReturned = cursor;
cursor++;
return value;
~~~

Phần đọc được thực hiện sau khi đã kiểm tra giới hạn. Không tăng con trỏ trước rồi mới phát hiện hết, và không dùng `ArrayIndexOutOfBoundsException` của kho mảng thay cho `NoSuchElementException` của iterator.

Một `next` hợp lệ trả `null` vẫn là một lần đọc thành công. Sau đó `remove` có thể xóa phần tử `null` vừa đọc nếu iterator hỗ trợ xóa.

## remove trên mảng: phải tính đến phần tử bị dồn

Trước khi xóa `B`:

~~~text
Chỉ số:         0   1   2   3
Dữ liệu:       [A,  B,  C,  D]
                       ^
cursor = 2 ------------+
lastReturned = 1
~~~

`cursor = 2` nghĩa là lần tới đọc `C`. Khi xóa tại chỉ số `1`, `C` và `D` dồn sang trái:

~~~text
Chỉ số:         0   1   2
Dữ liệu:       [A,  C,  D]
                   ^
cursor mới = 1 -+
~~~

Nếu giữ `cursor = 2`, lần tiếp theo trả `D` và bỏ sót `C`. Vì vậy, sau khi xóa thành công:

~~~java
cursor = lastReturned;
lastReturned = -1;
~~~

Đối với iterator đi tới trong ví dụ, `lastReturned` bằng `cursor - 1` ngay trước lúc xóa, nên đặt `cursor = lastReturned` tương đương lùi con trỏ một vị trí. Viết theo đích xóa giúp lý do rõ hơn.

`lastReturned = -1` ngăn xóa hai lần sau cùng một `next`. Nếu chỉ chỉnh con trỏ mà quên xóa dấu đích cũ, lần `remove` tiếp theo có thể xóa phần tử vừa bị dồn vào vị trí đó.

### Ba bước xóa dữ liệu và một bước giữ trạng thái

Hàm xóa của kho mảng cần:

1. Dồn đoạn sau đích xóa sang trái.
2. Giảm `size`.
3. Xóa tham chiếu ở ô đuôi không còn được dùng.
4. Tăng phiên bản thay đổi cấu trúc.

Ví dụ với `[A,B,C,D]` có dung lượng mảng lớn hơn bốn, sau khi xóa `B`, phần hoạt động là `[A,C,D]`. Ô cũ từng giữ `D` ở phía sau `size` mới phải được đặt thành `null`.

Đặt ô đuôi thành `null` không “xóa đối tượng khỏi JVM”. Nó chỉ bỏ một tham chiếu không còn cần từ mảng. Đối tượng vẫn sống nếu nơi khác còn giữ tham chiếu, chẳng hạn biến được `next` trả trước đó.

Phần cập nhật trạng thái iterator chỉ thực hiện sau khi thao tác xóa dữ liệu thành công. Không đặt `lastReturned = -1` rồi mới làm một thao tác có thể thất bại và khiến iterator không còn biết nó đã thực sự xóa hay chưa.

## Xóa theo vị trí, không xóa theo equals

Một cách viết dễ sai:

~~~java
@Override
public void remove() {
    collection.remove(lastValue);
}
~~~

Đây là minh họa lỗi nếu collection có phần tử bằng nhau và `remove(Object)` xóa phần tử bằng nhau đầu tiên.

Giả sử dữ liệu có:

~~~text
[X#first, X#second, Y#tail]
~~~

Hai đối tượng `X#first` và `X#second` khác định danh nhưng `equals` coi chúng bằng nhau. Iterator đã đọc cả hai và vừa trả `X#second`.

`Iterator.remove` phải xóa đúng lần xuất hiện vừa được trả, để lại `X#first`. Nếu gọi `collection.remove(lastValue)`, nó có thể tìm từ đầu và xóa `X#first`.

Lưu vị trí hoặc nút vừa trả là cách liên kết thao tác xóa với đúng phần tử của lượt duyệt. Một giá trị so sánh bằng nhau không đủ để xác định vị trí.

Bài toán tương tự xuất hiện với map entry, hàng đợi có phần tử trùng hoặc một view qua bộ lọc. Trước khi ủy quyền `remove`, phải biết đối tượng được ủy quyền còn đang chỉ đúng phần tử mà iterator ngoài đã trả hay không.

## Thay đổi cấu trúc và expectedModCount

Nếu collection bị thêm hoặc xóa trực tiếp trong khi iterator đang giữ chỉ số, các chỉ số có thể không còn mô tả đúng đoạn dữ liệu đã duyệt. Một chính sách thông dụng là phát hiện và từ chối tiếp tục, thường gọi là fail-fast.

Ví dụ dùng:

~~~text
Collection:
    modCount

Mỗi iterator:
    expectedModCount
~~~

Mỗi lần thêm hoặc xóa thành công, collection tăng `modCount`. Iterator ghi nhớ phiên bản lúc được tạo. Trước `next` và trước một `remove` có đích hợp lệ, nó so sánh hai số. Nếu khác, nó ném `ConcurrentModificationException`.

### Vì sao iterator tự xóa không làm chính nó hỏng?

`remove` hợp lệ cũng đổi cấu trúc, nên `modCount` tăng. Iterator biết chính nó đã thực hiện thay đổi và đã sửa con trỏ. Vì vậy sau xóa, nó cập nhật:

~~~java
expectedModCount = modCount;
~~~

Nếu quên dòng này, chính lần `next` sau khi iterator xóa hợp lệ sẽ báo lỗi thay đổi cấu trúc.

Nếu có hai iterator, mỗi iterator giữ phiên bản riêng. Iterator thứ nhất xóa và tự đồng bộ phiên bản của nó. Iterator thứ hai không được tự động sửa con trỏ; nó vẫn giữ phiên bản cũ và sẽ bị phát hiện khi đi tới điểm kiểm tra.

Không cập nhật phiên bản kỳ vọng của mọi iterator để “tránh lỗi”. Làm vậy chỉ che việc con trỏ của iterator khác chưa được điều chỉnh.

### Fail-fast không phải cơ chế đồng bộ

Một số phiên bản bằng nhau không chứng minh không có tranh chấp dữ liệu. Một bộ đếm `int` không tạo khóa, không làm các thao tác đọc/ghi thành giao dịch, và không cung cấp chính sách truy cập đồng thời an toàn.

`ConcurrentModificationException` có thể xuất hiện ngay trong một luồng nếu luồng đó sửa collection trực tiếp rồi tiếp tục dùng iterator cũ. Ngược lại, khi cập nhật không có đồng bộ giữa nhiều luồng, không được dựa vào việc ngoại lệ chắc chắn xuất hiện. Tài liệu [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) nêu rõ đây là cơ chế hỗ trợ phát hiện lỗi theo khả năng quan sát được.

Với collection tự viết, cần công bố riêng chính sách đồng thời. Ví dụ trong bài dành cho sử dụng tuần tự hoặc đồng bộ bên ngoài đúng cách; không cung cấp iterator snapshot hay iterator cho cập nhật đồng thời.

## Chương trình đầy đủ: viết iterator có remove

Lưu vào `IteratorCursorDemo.java`. Chương trình dùng Java 17+, không có thư viện ngoài.

`ArrayBag` là collection dung lượng cố định để phần quản lý tăng kích thước mảng không làm nhiễu bài học. Nó cho phép trùng và `null`, duyệt theo thứ tự được thêm. Khi đầy, `add` ném `IllegalStateException`. Hàm tiện ích `bag(...)` tạo đủ dung lượng cho các thí nghiệm nhỏ.

`Cursor` là lớp trong không `static`, nên truy cập đúng dữ liệu của đối tượng `ArrayBag` chứa nó. Mỗi lần `iterator()` tạo một `Cursor` mới với trạng thái riêng.

Các phép thử gồm xóa giữa/cuối, xóa liên tiếp, phần tử trùng theo `equals`, hai iterator, thay đổi ngoài iterator, dữ liệu `null`, iterator chỉ đọc, `removeIf`, `forEachRemaining` và một đoạn dùng `ListIterator` chuẩn để đối chiếu con trỏ hai chiều.

~~~java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Collection;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;
import java.util.Objects;

public class IteratorCursorDemo {
    static final class ArrayBag<E> extends AbstractCollection<E> {
        private final Object[] elements;
        private int size;
        private int modCount;

        ArrayBag(int capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("negative capacity");
            }
            elements = new Object[capacity];
        }

        @Override public int size() {
            return size;
        }

        @Override public boolean add(E value) {
            if (size == elements.length) {
                throw new IllegalStateException("bag is full");
            }
            elements[size++] = value;
            modCount++;
            return true;
        }

        private void removeAt(int index) {
            Objects.checkIndex(index, size);
            int moved = size - index - 1;
            if (moved > 0) {
                System.arraycopy(elements, index + 1, elements, index, moved);
            }
            elements[--size] = null;
            modCount++;
        }

        @SuppressWarnings("unchecked")
        private E elementAt(int index) {
            return (E) elements[index];
        }

        @Override public Iterator<E> iterator() {
            return new Cursor();
        }

        private final class Cursor implements Iterator<E> {
            private int cursor;
            private int lastReturned = -1;
            private int expectedModCount = modCount;

            private void checkForModification() {
                if (expectedModCount != modCount) {
                    throw new ConcurrentModificationException();
                }
            }

            @Override public boolean hasNext() {
                return cursor < size;
            }

            @Override public E next() {
                checkForModification();
                if (cursor >= size) {
                    throw new NoSuchElementException();
                }
                E value = elementAt(cursor);
                lastReturned = cursor;
                cursor++;
                return value;
            }

            @Override public void remove() {
                if (lastReturned < 0) {
                    throw new IllegalStateException();
                }
                checkForModification();
                removeAt(lastReturned);
                cursor = lastReturned;
                lastReturned = -1;
                expectedModCount = modCount;
            }
        }
    }

    static final class Token {
        private final String value;
        private final String tag;

        Token(String value, String tag) {
            this.value = value;
            this.tag = tag;
        }

        @Override public boolean equals(Object other) {
            return other instanceof Token token && value.equals(token.value);
        }

        @Override public int hashCode() {
            return value.hashCode();
        }

        @Override public String toString() {
            return value + "#" + tag;
        }
    }

    @SafeVarargs
    static <E> ArrayBag<E> bag(E... values) {
        ArrayBag<E> bag = new ArrayBag<>(Math.max(16, values.length));
        for (E value : values) {
            bag.add(value);
        }
        return bag;
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static <E> Iterator<E> readOnly(Iterator<E> source) {
        return new Iterator<>() {
            @Override public boolean hasNext() { return source.hasNext(); }
            @Override public E next() { return source.next(); }
        };
    }

    public static void main(String[] args) {
        ArrayBag<String> words = bag("A", "B", "C", "D");
        Iterator<String> it = words.iterator();
        System.out.println("remove-before-next = " + outcome(it::remove));
        System.out.println("repeated-hasNext = " + it.hasNext() + "," + it.hasNext());
        System.out.println("first = " + it.next());
        System.out.println("second = " + it.next());
        it.remove();
        System.out.println("after-remove-B = " + words);
        System.out.println("next-after-shift = " + it.next());
        it.remove();
        System.out.println("after-remove-C = " + words);
        System.out.println("remove-twice = " + outcome(it::remove));
        System.out.println("last = " + it.next());
        System.out.println("hasNext-at-end = " + it.hasNext());
        it.remove();
        System.out.println("after-remove-last = " + words);
        System.out.println("next-at-end = " + outcome(it::next));

        ArrayBag<Integer> all = bag(1, 2, 3, 4);
        List<Integer> visited = new ArrayList<>();
        Iterator<Integer> every = all.iterator();
        while (every.hasNext()) {
            visited.add(every.next());
            every.remove();
        }
        System.out.println("remove-all-visited = " + visited);
        System.out.println("remove-all-result = " + all);

        Token first = new Token("X", "first");
        Token second = new Token("X", "second");
        ArrayBag<Token> duplicates = bag(first, second, new Token("Y", "tail"));
        Iterator<Token> duplicateIt = duplicates.iterator();
        duplicateIt.next();
        System.out.println("duplicate-last-returned = " + duplicateIt.next());
        duplicateIt.remove();
        System.out.println("duplicate-after-remove = " + duplicates);

        ArrayBag<String> shared = bag("A", "B", "C");
        Iterator<String> left = shared.iterator();
        Iterator<String> right = shared.iterator();
        System.out.println("independent-first = " + left.next() + "," + right.next());
        left.remove();
        System.out.println("removing-iterator-continues = " + left.next());
        System.out.println("other-iterator = " + outcome(right::next));
        Iterator<String> stale = shared.iterator();
        shared.add("D");
        System.out.println("external-add = " + outcome(stale::next));

        ArrayBag<String> nullable = bag(null, "tail");
        Iterator<String> nullableIt = nullable.iterator();
        System.out.println("null-is-value = " + nullableIt.next());
        System.out.println("after-null-hasNext = " + nullableIt.hasNext());
        nullableIt.remove();
        System.out.println("after-remove-null = " + nullable);

        Iterator<String> readOnly = readOnly(bag("R").iterator());
        System.out.println("read-only-next = " + readOnly.next());
        System.out.println("read-only-remove = " + outcome(readOnly::remove));
        Iterator<String> empty = IteratorCursorDemo.<String>bag().iterator();
        System.out.println("empty-hasNext = " + empty.hasNext());
        System.out.println("empty-next = " + outcome(empty::next));

        ArrayBag<Integer> numbers = bag(1, 2, 3, 4, 5, 6);
        System.out.println("removeIf-changed = " + numbers.removeIf(n -> n % 2 == 0));
        System.out.println("removeIf-result = " + numbers);
        Iterator<String> rest = bag("F", "G", "H").iterator();
        System.out.println("before-forEachRemaining = " + rest.next());
        List<String> remaining = new ArrayList<>();
        rest.forEachRemaining(remaining::add);
        System.out.println("forEachRemaining-result = " + remaining);
        System.out.println("forEachRemaining-null = "
                + outcome(() -> rest.forEachRemaining(null)));

        List<String> list = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> both = list.listIterator(2);
        System.out.println("list-previous = " + both.previous());
        both.remove();
        System.out.println("list-next-after-remove = " + both.next());
        System.out.println("list-previous-again = " + both.previous());
        both.set("X");
        both.add("Y");
        System.out.println("list-after-set-add = " + list);
        System.out.println("list-set-after-add = " + outcome(() -> both.set("Z")));
        System.out.println("list-previous-after-add = " + both.previous());
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 IteratorCursorDemo.java
java IteratorCursorDemo
~~~

Mã đã được biên dịch với `--release 17` và chạy bằng OpenJDK Zulu 24.0.2. Stdout chính xác:

~~~text
remove-before-next = IllegalStateException
repeated-hasNext = true,true
first = A
second = B
after-remove-B = [A, C, D]
next-after-shift = C
after-remove-C = [A, D]
remove-twice = IllegalStateException
last = D
hasNext-at-end = false
after-remove-last = [A]
next-at-end = NoSuchElementException
remove-all-visited = [1, 2, 3, 4]
remove-all-result = []
duplicate-last-returned = X#second
duplicate-after-remove = [X#first, Y#tail]
independent-first = A,A
removing-iterator-continues = B
other-iterator = ConcurrentModificationException
external-add = ConcurrentModificationException
null-is-value = null
after-null-hasNext = true
after-remove-null = [tail]
read-only-next = R
read-only-remove = UnsupportedOperationException
empty-hasNext = false
empty-next = NoSuchElementException
removeIf-changed = true
removeIf-result = [1, 3, 5]
before-forEachRemaining = F
forEachRemaining-result = [G, H]
forEachRemaining-null = NullPointerException
list-previous = B
list-next-after-remove = C
list-previous-again = C
list-after-set-add = [A, Y, X]
list-set-after-add = IllegalStateException
list-previous-after-add = Y
~~~

## Đọc kết quả theo trạng thái con trỏ

### hasNext không tiêu thụ phần tử

`repeated-hasNext = true,true` được in trước khi đọc. Hai lần kiểm tra không làm mất `A`; `first = A` vẫn là phần tử đầu.

`remove-before-next = IllegalStateException` xác nhận chưa có đích xóa hợp lệ. Đây là iterator có hỗ trợ `remove` nhưng lời gọi diễn ra sai trạng thái, khác trường hợp iterator chỉ đọc không hỗ trợ thao tác.

### Xóa không làm bỏ qua phần tử dồn vào

Sau khi đọc `A` và `B`, `remove` để lại `[A,C,D]`. Dòng `next-after-shift = C` là bằng chứng con trỏ đã được trả về vị trí chứa `C` mới.

Xóa tiếp `C` để lại `[A,D]`. Một lần xóa nữa mà chưa đọc thêm nhận `IllegalStateException`. Sau đó iterator vẫn đọc được `D`.

`hasNext-at-end = false` xuất hiện sau khi trả `D`. Dù không còn phần tử tiếp theo, `remove` vẫn xóa `D` và collection còn `[A]`. Không dùng `hasNext` làm điều kiện quyết định có được xóa phần tử vừa trả hay không.

### Xóa mọi phần tử kiểm tra cả biên đầu và biên rỗng

Vòng lặp đọc rồi xóa từng phần tử thu được `[1,2,3,4]` đầy đủ và collection cuối `[]`. Nếu quên lùi con trỏ sau mỗi lần dồn mảng, phép thử thường bỏ qua một số phần tử.

Nó cũng kiểm tra rằng khi xóa phần tử ở chỉ số không, các phần tử sau được xử lý đúng; và sau lần xóa cuối, `cursor` cùng `size` đều trở về không.

### Hai phần tử bằng nhau vẫn phải xóa đúng lần xuất hiện

`Token.equals` chỉ so trường `value`, còn `tag` giúp nhìn thấy từng đối tượng trong stdout.

Iterator vừa trả `X#second`. Sau xóa, kết quả `[X#first,Y#tail]` cho thấy đích xóa được xác định bằng vị trí vừa trả. Việc giữ lại `X#second` và xóa `X#first` sẽ là sai, dù một phép so sánh danh sách chỉ dựa trên `equals` có thể không phát hiện.

Với kiểm thử cấu trúc có phần tử trùng, nên có dữ liệu phân biệt được định danh hoặc vị trí. Chỉ thử các chuỗi khác nhau chưa kiểm tra được lỗi xóa theo giá trị.

### Hai iterator có con trỏ và phiên bản độc lập

`independent-first = A,A` cho thấy hai iterator cùng bắt đầu từ đầu, không dùng chung một biến chỉ số trong collection.

Sau khi `left` xóa `A`, chính nó tiếp tục trả `B` vì đã điều chỉnh con trỏ và phiên bản. `right` giữ phiên bản cũ, nên `right.next` ném `ConcurrentModificationException`.

Tạo một iterator khác rồi gọi `shared.add("D")` trực tiếp cũng làm iterator cũ bị từ chối ở `next`. Đây là phép thử đơn luồng có thứ tự xác định, không phải phép thử lịch chạy ngẫu nhiên giữa nhiều luồng.

### null không phải hết dữ liệu

`null-is-value = null` là kết quả đọc thành công. `after-null-hasNext = true` cho biết `tail` vẫn còn.

Sau `nullableIt.remove`, collection là `[tail]`. Nếu dùng `lastValue == null` để suy ra chưa gọi `next`, iterator sẽ từ chối nhầm lần xóa này. Biến `lastReturned = -1` tránh việc trộn trạng thái điều khiển với giá trị dữ liệu.

### Iterator chỉ đọc có hợp đồng khác về remove

Hàm `readOnly` chỉ ủy quyền `hasNext` và `next`, giữ phần cài đặt mặc định của `Iterator.remove`. Nó đọc `R` được nhưng xóa nhận `UnsupportedOperationException`.

Đây là một lớp bọc minh họa, không biến toàn bộ collection gốc thành collection bất biến: nếu nơi khác còn giữ collection, nơi đó có thể sửa theo API được phép. Nó chỉ chặn xóa qua iterator được trả.

### Các thao tác kế thừa dùng được khi iterator đúng

`ArrayBag` không tự viết `removeIf`. Phần mặc định của `Collection` dùng iterator và xóa các phần tử thỏa điều kiện. Kết quả `[1,3,5]` cho thấy việc xóa nhiều phần tử trong một lượt không làm hỏng con trỏ.

Các thao tác khác của `AbstractCollection` cũng có thể dựa vào iterator. Vì vậy, hỗ trợ `remove` đúng không chỉ phục vụ vòng lặp tự viết; nó còn mở khả năng cho các thao tác xóa kế thừa. Xem [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) và [Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

## Không trộn remove với các cách duyệt không cùng giao thức

### for-each che iterator khỏi phần thân

Với một `Iterable` thông thường, vòng `for-each` dùng một iterator để duyệt. Bên trong thân vòng, biến phần tử không phải iterator; gọi `collection.remove(value)` là sửa qua đường khác.

Đoạn minh họa cần tránh nếu collection không cho phép sửa ngoài giao thức duyệt:

~~~java
for (String value : values) {
    if (shouldDelete(value)) {
        values.remove(value);
    }
}
~~~

`shouldDelete` ở đây là điều kiện của ứng dụng. Cách viết rõ ràng khi muốn xóa qua iterator:

~~~java
Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if (shouldDelete(value)) {
        iterator.remove();
    }
}
~~~

Cách thứ hai vẫn cần iterator có hỗ trợ `remove`. Một collection chỉ đọc, một iterator snapshot hoặc một triển khai khác có thể từ chối. Không có quy tắc rằng mọi iterator của mọi collection đều sửa được.

Với trường hợp đơn giản, `values.removeIf(this::shouldDelete)` có thể thể hiện ý định gọn hơn nếu collection hỗ trợ. Tuy nhiên, callback không nên tự sửa chính collection đang được phương thức đó duyệt.

Cách dịch `for-each` với `Iterable` được nêu trong [JLS 14.14.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2). Đối với mảng, `for-each` có cơ chế khác và không tạo một `Iterator` cho phép gọi `remove`.

### forEachRemaining không phải vòng xóa qua iterator

`forEachRemaining` chuyển các phần tử còn lại cho một hành động. Trong chương trình, iterator đã đọc `F`, nên phần còn lại được gom là `[G,H]`.

Có ba giới hạn cần nhớ:

- Hành động không nên thay đổi collection nguồn, kể cả gọi `iterator.remove` từ trong callback, trừ khi triển khai công bố chính sách cho phép.
- Hành vi `remove` sau `forEachRemaining` không được hợp đồng `Iterator` tổng quát xác định.
- Nếu callback ném ngoại lệ, không giả định trạng thái tiếp tục của iterator vẫn có một ý nghĩa chung cho mọi triển khai.

Do đó, đừng suy ra rằng vì phần mặc định có hình thức “lặp `hasNext/next`” thì mọi cách xen `remove` đều được bảo đảm như vòng lặp tường minh. Với nhu cầu xóa, dùng vòng lặp `next/remove` hoặc `removeIf` theo đúng hợp đồng.

Chương trình không gọi `remove` sau `forEachRemaining`. Nó chỉ kiểm tra dữ liệu đã được chuyển và việc truyền hành động `null` nhận `NullPointerException`, kể cả iterator đã được duyệt hết. Các giới hạn này nằm trong [Iterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## Mở rộng sang ListIterator: con trỏ nằm giữa phần tử

`Iterator` đi tới chỉ cần khái niệm phần tử sẽ đọc tiếp. `ListIterator` còn đi lùi, thêm ở con trỏ và thay phần tử vừa trả. Vì vậy cần tách rõ con trỏ với phần tử đích của `remove/set`.

Với danh sách ba phần tử, có bốn vị trí con trỏ:

~~~text
Vị trí con trỏ:
    0     1     2     3
    |  A  |  B  |  C  |
~~~

Nếu `cursor = 2`:

- `next` trả `C` rồi đưa con trỏ thành `3`.
- `previous` trả `B` rồi đưa con trỏ thành `1`.

Không có “phần tử hiện tại” duy nhất tại con trỏ; nó là ranh giới giữa phần tử trước và sau. `remove/set` tác động đến phần tử mà `next` hoặc `previous` đã trả gần nhất. Xem [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### Công thức điều chỉnh sau xóa hai chiều

Với cách biểu diễn con trỏ là chỉ số phần tử mà `next` sẽ trả, giả sử `lastReturned` là chỉ số đích xóa trước khi dồn mảng:

~~~text
Xóa tại lastReturned:

nếu lastReturned < cursor:
    cursor giảm 1
ngược lại:
    cursor giữ nguyên

lastReturned = -1
~~~

Tại sao không luôn giảm?

- Sau `next`, phần tử vừa trả nằm trước con trỏ. Xóa nó làm các phần tử sau dồn trái, nên con trỏ cần giảm.
- Sau `previous`, phần tử vừa trả nằm ngay tại chỉ số con trỏ mới. Xóa nó làm phần tử kế tiếp dồn vào đúng chỉ số đó, nên giữ con trỏ.

Trong mô hình mảng này, đặt `cursor = lastReturned` sau xóa cũng cho kết quả đúng ở cả hai hướng vì quan hệ giữa hai biến thay đổi theo hướng vừa đi. Điều không được áp dụng máy móc là luôn thực hiện `cursor--`: sau `previous`, cách đó sẽ lùi quá một vị trí. Khi đổi cách biểu diễn con trỏ hoặc chuyển sang các nút liên kết, phải suy ra cập nhật từ đúng bất biến của cấu trúc đó.

### add và set có tác động trạng thái khác nhau

`ListIterator.add(e)` chèn trước phần tử mà `next` sẽ trả và sau phần tử mà `previous` sẽ trả. Theo chỉ số, thêm tại `cursor` rồi tăng `cursor` để con trỏ nằm sau phần tử mới.

Sau thêm:

- Một lần `next` vẫn đi tới phần tử vốn ở phía sau con trỏ.
- Một lần `previous` trả phần tử vừa thêm.
- Không được `remove` hoặc `set` dựa trên lần đọc trước thao tác thêm; phải có lần `next/previous` mới.

`set(e)` chỉ thay phần tử vừa trả, không dịch con trỏ và không thêm/xóa vị trí. Nếu được hỗ trợ, nó không tự tiêu thụ quyền `set` như `remove` tiêu thụ quyền xóa. Nhưng `remove/add` sau lần đọc làm điều kiện `set` trước đó hết hiệu lực.

Đoạn cuối chương trình dùng `ArrayList.listIterator(2)`:

1. `previous` trả `B`.
2. Xóa `B`.
3. `next` trả `C`, không bỏ qua nó.
4. `previous` lại trả `C`.
5. `set("X")` thay `C` bằng `X`.
6. `add("Y")` tạo `[A,Y,X]`.
7. `set` ngay sau `add` nhận `IllegalStateException`.
8. `previous` trả `Y`, tức phần tử vừa thêm.

Đây là đối chiếu hành vi của API chuẩn. Lớp `ArrayBag.Cursor` trong bài chỉ cài `Iterator` đi tới, không công bố hỗ trợ `previous/add/set`.

## Nếu kho dữ liệu là các nút liên kết

Với danh sách liên kết, xóa một nút thường không dồn cả đoạn dữ liệu. Nhưng trạng thái đích xóa vẫn cần được giữ.

Ví dụ:

~~~text
A -> B -> C -> D

đã trả B
nút sẽ trả tiếp = C
nút vừa trả    = B
~~~

Xóa `B` phải nối đường từ `A` tới `C`, còn vị trí đi tiếp vẫn là `C`.

Với liên kết đơn, iterator thường cần đủ thông tin để tìm nút đứng trước đích xóa, hoặc dùng cấu trúc sentinel và theo dõi các nút tiền nhiệm. Chỉ giữ `nextNode` chưa chắc đủ để xóa nút vừa trả trong thời gian hằng số.

Các trường hợp phải xét riêng:

- Xóa nút đầu: cập nhật đầu danh sách.
- Xóa nút cuối: cập nhật đuôi nếu có.
- Xóa nút duy nhất: đầu và đuôi trở về trạng thái rỗng.
- Xóa nhiều nút liên tiếp qua iterator: tiền nhiệm và đích mới không được trỏ vào nút đã tháo.
- Hai iterator: thay đổi qua một iterator không tự sửa con trỏ của iterator kia.

Với liên kết đôi, biết đúng nút có thể giúp nối lại hai phía, nhưng `ListIterator` vẫn phải cập nhật vị trí và hướng vừa duyệt đúng. Cấu trúc dữ liệu khác nhau thay đổi thuật toán xóa, không bỏ được hợp đồng của iterator. `LinkedList` chuẩn là một ví dụ danh sách liên kết đôi có iterator và list iterator, được mô tả trong [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## Iterator bọc và việc đọc trước trong hasNext

Đối với iterator trên mảng, `hasNext` chỉ so sánh chỉ số. Với iterator lọc dữ liệu, để biết có phần tử phù hợp hay không, `hasNext` có thể cần đọc trước từ một iterator bên dưới và giữ phần tử đó trong bộ nhớ đệm.

Đọc trước là được nếu hợp đồng quan sát bên ngoài vẫn đúng: gọi `hasNext` nhiều lần không làm bỏ phần tử, `next` trả phần tử đã giữ, và hết dữ liệu được báo chính xác.

Nhưng `remove` trở nên khó hơn. Hình dung:

1. Iterator ngoài trả phần tử `A`.
2. Bên gọi hỏi `hasNext`.
3. Iterator ngoài dùng `delegate.next` nhiều lần để tìm phần tử phù hợp tiếp theo `C`.
4. Bên gọi yêu cầu `remove` của iterator ngoài để xóa `A`.

Nếu lúc này chỉ gọi `delegate.remove`, đích của delegate có thể là `C`, không còn là `A`. Chỉ ủy quyền tên phương thức giống nhau là chưa đủ.

Có ba hướng thiết kế:

- Không hỗ trợ `remove` ở lớp bọc và công bố rõ.
- Giữ cơ chế xóa chính xác đích đã trả, với kho hoặc giao thức cho phép điều đó.
- Thiết kế lại cách duyệt/đọc trước sao cho giữ được hợp đồng đã công bố.

Không được bí mật xóa phần tử khác vì “iterator bên dưới chỉ xóa được phần tử gần nhất”. Việc hỗ trợ thao tác tùy chọn là lựa chọn; xóa đúng đích khi đã hỗ trợ là nghĩa vụ.

Tương tự, một iterator snapshot không nên tự gọi `source.remove(value)` để giả lập xóa nếu việc đó không xác định được đúng lần xuất hiện và vòng đời của phần tử gốc.

## Những lỗi cài đặt thường gặp

| Lỗi | Hậu quả | Cách sửa theo mô hình trong bài |
| --- | --- | --- |
| `hasNext` tăng `cursor` | Kiểm tra làm mất phần tử | Chỉ quan sát; nếu đọc trước thì phải giữ bộ đệm ổn định |
| `next` tin rằng bên gọi luôn kiểm tra trước | Hết dữ liệu gây lỗi kho hoặc trả kết quả sai | Tự kiểm tra và ném `NoSuchElementException` |
| Dùng `null` làm dấu chưa đọc | Không xóa được phần tử `null` hợp lệ | Giữ cờ/chỉ số trạng thái riêng |
| Xóa mảng nhưng không sửa `cursor` | Bỏ qua phần tử vừa dồn trái | Đưa con trỏ về đúng vị trí cần đọc tiếp |
| Quên đặt lại `lastReturned` | Xóa hai lần sau một lần đọc | Xóa đích hợp lệ sau `remove` thành công |
| Gọi `remove(Object)` theo giá trị | Xóa nhầm lần xuất hiện bằng nhau | Xóa theo chỉ số/nút đã trả |
| Quên cập nhật phiên bản kỳ vọng sau tự xóa | Iterator tự báo lỗi ở lượt tiếp | Đồng bộ phiên bản của chính iterator vừa điều chỉnh |
| Dùng chung cursor cho mọi iterator | Hai vòng duyệt làm lệch nhau | Trạng thái nằm trong từng đối tượng iterator |
| Không xóa ô mảng dư | Giữ tham chiếu không còn cần | Đặt ô sau đoạn hoạt động thành `null` |
| Nuốt lỗi thay đổi rồi tiếp tục với chỉ số cũ | Đọc/xóa sai dữ liệu | Không tự phục hồi nếu chưa có giao thức sửa trạng thái |

Một lỗi khác là trả chính đối tượng iterator đã dùng dở từ mọi lần `collection.iterator()`. Với một collection thông thường hỗ trợ nhiều lượt duyệt, các lượt cần trạng thái riêng. Hai vòng `for-each` lồng nhau không nên dùng chung một con trỏ.

Một nguồn dữ liệu một lượt có thể có hợp đồng khác, nhưng phải mô tả rõ đó là nguồn một lượt. Không đem lựa chọn ấy áp vào một collection mà bên dùng mong đợi tạo được các lượt duyệt độc lập. Vai trò của `Iterable.iterator` và vòng lặp được giới thiệu trong [Iterable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html).

## Cách kiểm tra iterator có hỗ trợ remove

Kiểm tra theo chuỗi thao tác, không chỉ theo từng phương thức độc lập.

### Chuỗi trạng thái cơ bản

~~~text
tạo iterator
-> remove: lỗi trạng thái
-> hasNext, hasNext: không di chuyển
-> next: nhận phần tử đầu
-> remove: xóa được
-> remove: lỗi trạng thái
-> next: nhận phần tử tiếp theo đúng
~~~

Lặp lại trên collection rỗng, một phần tử và nhiều phần tử. Với một phần tử, cần kiểm tra trường hợp đã hết phần tử phía trước nhưng vẫn xóa được phần tử vừa trả.

### Chuỗi dữ liệu có phần tử trùng và null

Dùng hai đối tượng bằng nhau nhưng nhận diện được khác nhau; đọc tới đối tượng thứ hai rồi xóa. Xác nhận còn đúng đối tượng thứ nhất.

Dùng một phần tử `null` nếu collection cho phép. Đọc `null` phải thành công, lần kiểm tra tiếp theo phải đúng, và xóa `null` phải tuân thủ cùng quy tắc trạng thái.

### Chuỗi làm thay đổi cấu trúc

Với chính sách fail-fast đã công bố:

- Tạo iterator, sửa collection trực tiếp, rồi gọi điểm kiểm tra của iterator.
- Tạo hai iterator, xóa qua một iterator, xác nhận iterator đó vẫn đi tiếp đúng.
- Xác nhận iterator còn lại không được âm thầm tự đồng bộ mà không sửa con trỏ.
- Kiểm tra riêng thao tác thất bại không làm tăng phiên bản như thể cấu trúc đã đổi.

Các kiểm tra tuần tự này tìm lỗi logic con trỏ tốt hơn một bài thử nhiều luồng ngẫu nhiên. Nếu cần hỗ trợ cập nhật đồng thời, phải có thiết kế và kiểm thử đúng loại đồng thời đó, không chỉ bổ sung bộ đếm.

### Chuỗi tương tác với phương thức kế thừa

Thử `remove(Object)`, `removeIf`, `clear` và những thao tác kế thừa mà collection công bố hỗ trợ. Nếu chúng dựa vào iterator, lỗi con trỏ có thể xuất hiện dưới một tên phương thức khác.

Đừng tuyên bố thao tác hàng loạt có tính hoàn tác nếu chưa thiết kế điều đó. Khi callback hoặc bước xử lý ném lỗi, một số phần tử có thể đã bị xóa trước đó. Giao thức iterator bảo đảm đích xóa và trạng thái duyệt trong điều kiện đã công bố, không cung cấp giao dịch nghiệp vụ.

## Bài tập tự kiểm tra

### 1. Tại sao xóa B rồi next lại trả D là sai?

Collection `[A,B,C,D]`, iterator đã trả `B`, sau đó xóa `B` và `next` trả `D`.

**Đáp án:** `C` bị dồn từ chỉ số 2 về 1 nhưng con trỏ vẫn giữ 2. Cần đưa con trỏ về vị trí chứa phần tử tiếp theo sau khi dồn, trong mô hình đi tới là `cursor = lastReturned`.

### 2. hasNext trả false rồi có được remove không?

Iterator vừa trả phần tử cuối, chưa xóa nó, và xác nhận không còn phần tử tiếp theo.

**Đáp án:** Có, nếu iterator hỗ trợ xóa và chưa có sự kiện làm mất điều kiện đó. `hasNext` chỉ quan sát phần phía trước; nó không xóa dấu phần tử vừa trả.

### 3. Vì sao không dùng lastValue == null để kiểm tra chưa gọi next?

Collection cho phép `null` và iterator vừa trả một phần tử `null`.

**Đáp án:** `null` lúc này là dữ liệu hợp lệ. Phải giữ trạng thái riêng như `lastReturned = -1` hoặc một cờ hợp lệ, không trộn với giá trị phần tử.

### 4. Xóa theo equals có đủ không?

Iterator vừa trả đối tượng thứ hai trong hai đối tượng bằng nhau. `collection.remove(lastValue)` xóa đối tượng bằng nhau đầu tiên.

**Đáp án:** Không đủ. `Iterator.remove` xóa đúng lần xuất hiện vừa được trả. Cần giữ vị trí hoặc nút, không chỉ giữ giá trị dùng cho tìm kiếm.

### 5. Iterator tự xóa rồi bị CME ở next vì sao?

Xóa đã chỉnh con trỏ và tăng `modCount` nhưng chưa cập nhật `expectedModCount`.

**Đáp án:** Iterator đang so phiên bản cũ với thay đổi do chính nó thực hiện. Sau khi sửa dữ liệu và trạng thái thành công, cập nhật phiên bản kỳ vọng của iterator đó.

### 6. Hai iterator có nên dùng chung cursor không?

Một vòng duyệt đọc một phần tử và vòng duyệt khác bắt đầu từ cùng collection.

**Đáp án:** Với collection hỗ trợ các lượt độc lập, không. Dữ liệu và phiên bản cấu trúc thuộc collection; con trỏ, phần tử vừa trả và phiên bản kỳ vọng thuộc từng iterator.

### 7. ListIterator.previous rồi remove có luôn giảm cursor không?

Con trỏ là chỉ số của phần tử sẽ được `next` trả. `previous` vừa giảm con trỏ rồi trả phần tử tại vị trí mới.

**Đáp án:** Không luôn giảm. Khi xóa phần tử nằm tại con trỏ sau `previous`, giữ chỉ số để phần tử kế tiếp dồn vào đó. Chỉ giảm khi đích xóa nằm trước con trỏ theo mô hình chỉ số đã chọn.

### 8. Có thể gọi iterator.remove trong forEachRemaining không?

Một callback muốn xóa từng phần tử vừa nhận bằng `iterator.remove`.

**Đáp án:** Không dựa vào hợp đồng `Iterator` tổng quát để làm vậy. Hành vi callback sửa nguồn không được xác định nếu triển khai không công bố chính sách riêng; `remove` sau `forEachRemaining` cũng không có bảo đảm chung. Dùng vòng `next/remove` tường minh hoặc `removeIf` phù hợp.
