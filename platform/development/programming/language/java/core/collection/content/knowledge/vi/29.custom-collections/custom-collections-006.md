# modCount và việc phát hiện thay đổi cấu trúc khi phù hợp

## 1. Vấn đề cần giải quyết khi tự cài đặt collection

Một iterator phải nhớ nó đang đứng ở đâu. Với danh sách dựa trên chỉ số, nó có thể lưu vị trí phần tử kế tiếp; với danh sách liên kết, nó có thể giữ tham chiếu tới nút tiếp theo. Nếu collection bị chèn, xóa hoặc tổ chức lại trong lúc iterator còn được sử dụng, thông tin đó có thể trở nên lỗi thời.

Ví dụ, danh sách ban đầu là `[A, B, C]`. Iterator đã trả về `A` và chuẩn bị đọc chỉ số `1`. Nếu một đoạn mã khác xóa phần tử đầu, danh sách thành `[B, C]`. Đọc tiếp chỉ số `1` sẽ trả về `C`, bỏ qua `B`. Các phương thức truy cập chỉ số vẫn có thể chạy bình thường, nhưng quá trình duyệt không còn tương ứng với giả định ban đầu.

Trong một collection thay đổi được, người thiết kế phải chọn chính sách cho tình huống này. Một lựa chọn phổ biến là **phát hiện thay đổi không được phép rồi báo lỗi sớm**, gọi là fail-fast. Với lớp kế thừa `AbstractList`, trường được bảo vệ `modCount` hỗ trợ lựa chọn đó; lớp con có thể dùng các iterator mà lớp cha cung cấp. Đây là một phần của việc thiết kế hành vi collection, không phải một bước tự động có sẵn cho mọi lớp triển khai `Collection`. [AbstractList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

Bài học đi từ tình huống iterator bị lỗi thời đến ba việc thực hành:

1. Phân biệt thay đổi cấu trúc với thay thế một giá trị.
2. Cập nhật bộ đếm đúng ở lớp tùy chỉnh và hiểu giá trị kỳ vọng của từng iterator.
3. Kiểm tra các đường thay đổi gián tiếp, khung nhìn và giới hạn của fail-fast.

Kiến thức nền cần có là `List`, `Iterator`, `ListIterator`, kế thừa lớp trừu tượng và ngoại lệ. Các chương trình đầy đủ bên dưới dùng Java 17, không cần thư viện ngoài.

## 2. modCount ghi nhận điều gì?

### 2.1. Thay đổi cấu trúc và thay đổi giá trị

Trong ngữ cảnh danh sách, thêm hoặc xóa phần tử là thay đổi cấu trúc rõ ràng: số phần tử và quan hệ giữa chỉ số với phần tử đều có thể đổi. Khái niệm còn bao gồm những thay đổi làm xáo trộn cách duyệt đang diễn ra; không thể định nghĩa nó chỉ bằng phép so sánh hai giá trị `size()`.

Một phép `set(index, value)` của danh sách thông thường thay giá trị tại một vị trí đã tồn tại. Nó không chèn vị trí mới, không xóa vị trí cũ và thường không được tính là thay đổi cấu trúc. Chẳng hạn, tài liệu `ArrayList` phân biệt việc thêm/xóa hoặc thay đổi kích thước mảng lưu trữ với việc đặt lại giá trị phần tử. Chính sách cụ thể vẫn phải được đọc theo lớp đang sử dụng. [ArrayList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Trong lớp `TrackedList` sẽ xây dựng ở phần sau, ta chủ động chọn chính sách đơn giản:

| Thao tác của TrackedList | Có thay đổi cấu trúc? | Xử lý bộ đếm của lớp này |
| --- | --- | --- |
| `get(i)`, `size()` | Không | Giữ nguyên |
| `set(i, x)` với chỉ số hợp lệ | Không | Giữ nguyên |
| `add(i, x)` thành công | Có | Tăng một |
| `remove(i)` thành công | Có | Tăng một |
| `remove(Object)` không tìm thấy phần tử | Không có phần tử nào bị xóa | Giữ nguyên qua đường thực thi kế thừa |
| `add(i, x)` hoặc `remove(i)` thất bại do chỉ số sai | Không cập nhật dữ liệu | Giữ nguyên |
| Xóa một khoảng chứa hai phần tử bằng cách xóa từng phần tử | Có hai lần xóa cơ bản | Tăng hai qua hai lần `remove(int)` |

Bảng này là hợp đồng của ví dụ, không phải bảng quy định giá trị nội bộ của mọi lớp JDK. Những phép như tối ưu dung lượng, sắp xếp hoặc xử lý hàng loạt cần được xem xét theo chính sách và cách cài đặt riêng; không suy ra rằng “kích thước không đổi thì iterator chắc chắn còn dùng được”.

### 2.2. Không đồng nhất modCount với size hoặc số lần gọi phương thức

Hai danh sách có cùng kích thước cuối cùng vẫn có thể có lịch sử cấu trúc khác nhau:

```text
Trước: [A, B], size = 2
Xóa A: [B], size = 1
Chèn X: [X, B], size = 2
```

Iterator được tạo trước khi xóa không được phép kết luận rằng mọi thứ vẫn như cũ chỉ vì kích thước lại bằng `2`. Bộ đếm giúp nhận biết đã xảy ra thay đổi trong khoảng thời gian đó.

Ngược lại, gọi `get(0)` một trăm lần không tạo một trăm thay đổi cấu trúc. Trong ví dụ của bài, một lần `remove("missing")` cũng không tạo thay đổi nếu không tìm thấy phần tử. Thiết kế bộ đếm cần bám vào các đường cập nhật dữ liệu thực tế.

Giá trị này không phải mã định danh nghiệp vụ, số phiên bản bền vững hay nhật ký thay đổi. Không đưa nó vào API để người dùng suy luận danh sách đã từng chứa gì. Phương thức `revisionForDemo()` ở chương trình đầu chỉ phục vụ quan sát khi học.

### 2.3. Thay đổi đối tượng phần tử là vấn đề khác

Nếu một danh sách chứa các đối tượng thay đổi được, gọi một phương thức của đối tượng phần tử thường không đi qua phương thức thay đổi của danh sách. Bộ đếm cấu trúc không tự theo dõi mọi trường bên trong từng đối tượng.

Vì vậy, không có `ConcurrentModificationException` không chứng minh nội dung phần tử bất biến. Với phần tử làm khóa băm hoặc tham gia so sánh thứ tự, thay đổi trạng thái của chính phần tử còn có thể phá vỡ những giả định riêng của cấu trúc lưu trữ. Một bộ đếm trên collection không tự sửa được vấn đề đó.

## 3. Một bộ đếm của collection, một kỳ vọng cho mỗi iterator

Có thể hình dung hai vai trò:

- Collection giữ `modCount`: thông tin dùng chung về lịch sử thay đổi cấu trúc.
- Mỗi iterator giữ `expectedModCount`: giá trị mà iterator đó đang kỳ vọng.

Sơ đồ sau chỉ minh họa ý tưởng, không phải toàn bộ mã iterator:

```text
Tạo iterator:
    expectedModCount = modCount

Trước một bước cần kiểm tra:
    nếu modCount khác expectedModCount:
        báo ConcurrentModificationException

Sau khi iterator tự thực hiện một thay đổi được hỗ trợ:
    sửa lại vị trí duyệt
    expectedModCount = modCount
```

Trong mã nguồn OpenJDK 17 của `AbstractList`, `next()` kiểm tra bộ đếm trước khi đọc phần tử. `remove()` của iterator gọi đường xóa của danh sách, điều chỉnh con trỏ rồi nhận giá trị bộ đếm mới. `ListIterator` cũng quản lý kỳ vọng khi thực hiện các thao tác thay đổi của chính nó. Đây là mô tả cài đặt cụ thể dùng để giải thích thí nghiệm trong bài, không phải lời hứa rằng mọi iterator đều có cùng điểm kiểm tra. [Mã nguồn AbstractList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java)

Ví dụ với hai iterator `a` và `b`:

```text
Collection.modCount = 7
a.expected = 7
b.expected = 7

a xóa phần tử qua a.remove():
Collection.modCount = 8
a.expected = 8
b.expected = 7
```

Iterator `a` biết chính nó vừa xóa phần tử nào và đã điều chỉnh vị trí. Iterator `b` không được cập nhật kỳ vọng cùng với `a`; nó phải nhận ra dữ liệu mình dựa vào đã thay đổi. Nếu mọi iterator đều tự chấp nhận bộ đếm mới mỗi khi đọc, cơ chế phát hiện sẽ mất tác dụng.

Các giá trị `7`, `8` ở đây chỉ giúp giải thích quan hệ bằng/khác. Chương trình sử dụng collection không cần biết bộ đếm đang mang số cụ thể nào.

## 4. Cài đặt đúng khi kế thừa AbstractList

### 4.1. Đặt trách nhiệm ở các phép thêm và xóa cơ bản

Ví dụ này dùng một `ArrayList` riêng để lưu dữ liệu, nhưng trả iterator do `AbstractList` của lớp ngoài cung cấp. Vì vậy, bộ đếm nội bộ của `ArrayList` lưu trữ không thay thế được `modCount` của `TrackedList`.

Các phương thức cần chú ý:

- `get` và `size` đọc dữ liệu.
- `set` thay giá trị, giữ nguyên bộ đếm theo chính sách đã chọn.
- `add(int, E)` và `remove(int)` thay đổi dữ liệu thành công rồi tăng bộ đếm của lớp ngoài.
- Không trả `data` ra ngoài, để các đường thay đổi cấu trúc không bỏ qua trách nhiệm cập nhật bộ đếm.

Tài liệu `AbstractList` yêu cầu lớp con muốn dùng cơ chế fail-fast này phải cập nhật trường trong các phương thức thay đổi cấu trúc được ghi đè; một lần gọi phép thêm/xóa cơ bản được nêu trong hợp đồng không được tăng trường quá một. Với cách cài đặt dưới đây, mỗi phép cơ bản thành công tăng đúng một lần. [Hợp đồng modCount của AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

### 4.2. Chương trình đầy đủ

Lưu vào tệp `TrackedListDemo.java`. Mọi thao tác trong chương trình chạy tuần tự trên một luồng.

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;

public class TrackedListDemo {
    static final class TrackedList<E> extends AbstractList<E> {
        private final ArrayList<E> data = new ArrayList<>();

        @Override
        public E get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public E set(int index, E element) {
            return data.set(index, element);
        }

        @Override
        public void add(int index, E element) {
            data.add(index, element);
            modCount++;
        }

        @Override
        public E remove(int index) {
            E old = data.remove(index);
            modCount++;
            return old;
        }

        int revisionForDemo() {
            return modCount;
        }
    }

    private static void expectCme(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected CME: " + label);
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + "=CME");
        }
    }

    public static void main(String[] args) {
        TrackedList<Integer> list = new TrackedList<>();
        list.addAll(List.of(10, 20, 30));
        System.out.println("initial=" + list);
        System.out.println("revision=" + list.revisionForDemo());

        Iterator<Integer> first = list.iterator();
        System.out.println("first=" + first.next());
        list.set(1, 200);
        System.out.println("after-set revision=" + list.revisionForDemo());
        System.out.println("next-after-set=" + first.next());
        list.add(40);
        expectCme("external-add", () -> first.next());

        Iterator<Integer> owner = list.iterator();
        Iterator<Integer> observer = list.iterator();
        System.out.println("owner-next=" + owner.next());
        owner.remove();
        System.out.println("after-owner-remove=" + list);
        System.out.println("owner-continues=" + owner.next());
        expectCme("other-iterator", () -> observer.next());

        int beforeNoOp = list.revisionForDemo();
        System.out.println("remove-missing=" + list.remove(Integer.valueOf(999)));
        System.out.println("missing-keeps-revision="
                + (beforeNoOp == list.revisionForDemo()));
        try {
            list.remove(99);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("bad-index=IndexOutOfBoundsException");
        }
        System.out.println("failure-keeps-revision="
                + (beforeNoOp == list.revisionForDemo()));

        ListIterator<Integer> editor = list.listIterator();
        System.out.println("editor-next=" + editor.next());
        editor.set(201);
        editor.add(202);
        System.out.println("editor-continues=" + editor.next());
        System.out.println("after-editor=" + list);

        List<Integer> view = list.subList(1, 3);
        list.set(1, 222);
        System.out.println("view-after-set=" + view);
        view.remove(0);
        System.out.println("view-after-own-remove=" + view);
        System.out.println("root-after-view-remove=" + list);
        list.add(50);
        expectCme("old-view", () -> view.size());

        TrackedList<Integer> batch = new TrackedList<>();
        batch.addAll(List.of(1, 2, 3, 4));
        int batchStart = batch.revisionForDemo();
        batch.subList(1, 3).clear();
        System.out.println("batch=" + batch);
        System.out.println("batch-revision-delta="
                + (batch.revisionForDemo() - batchStart));
        int emptyStart = batch.revisionForDemo();
        batch.subList(1, 1).clear();
        System.out.println("empty-range-keeps-revision="
                + (emptyStart == batch.revisionForDemo()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TrackedListDemo.java
java TrackedListDemo
```

Stdout:

```text
initial=[10, 20, 30]
revision=3
first=10
after-set revision=3
next-after-set=200
external-add=CME
owner-next=10
after-owner-remove=[200, 30, 40]
owner-continues=200
other-iterator=CME
remove-missing=false
missing-keeps-revision=true
bad-index=IndexOutOfBoundsException
failure-keeps-revision=true
editor-next=200
editor-continues=30
after-editor=[201, 202, 30, 40]
view-after-set=[222, 30]
view-after-own-remove=[30]
root-after-view-remove=[201, 30, 40]
old-view=CME
batch=[1, 4]
batch-revision-delta=2
empty-range-keeps-revision=true
```

### 4.3. Đọc kết quả theo đường thay đổi dữ liệu

`revision=3` xuất hiện vì ví dụ thêm ba phần tử qua các phép thêm cơ bản. Sau `set(1, 200)`, bộ đếm vẫn bằng `3`; iterator đầu tiên đọc tiếp được giá trị mới `200`. Điều đó cũng cho thấy iterator này không giữ một bản sao độc lập của toàn bộ nội dung ban đầu.

Sau `list.add(40)`, iterator đầu tiên không còn có kỳ vọng phù hợp. Lời gọi `first.next()` báo lỗi trong thí nghiệm. Không có luồng thứ hai: thay đổi ngoài iterator trong cùng một luồng đã đủ tạo tình huống cần phát hiện.

`owner.remove()` xóa phần tử mà chính `owner` vừa trả về. Iterator này tiếp tục được, nhưng `observer`, vốn được tạo trước lần xóa, bị vô hiệu hóa. Đây là lý do chỉ cập nhật kỳ vọng cho iterator thực hiện thay đổi.

Tiếp theo, xóa giá trị không tồn tại trả về `false`; xóa theo chỉ số `99` báo `IndexOutOfBoundsException`. Hai dòng kiểm tra bộ đếm đều là `true`, vì các nhánh này không thực hiện một lần xóa thành công trong lớp ví dụ.

Phần `ListIterator` thay `200` thành `201`, chèn `202`, rồi tiếp tục đến `30`. Sau thao tác chèn, con trỏ nằm sau phần tử vừa chèn; không phải chương trình quên đọc `202`. Điều chỉnh vị trí và cập nhật kỳ vọng đều thuộc trách nhiệm iterator. Các quy tắc `set`, `add`, `remove` của `ListIterator` cần được tuân thủ cùng với cơ chế bộ đếm. [ListIterator trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html)

Hai đoạn cuối về khung nhìn và xóa khoảng sẽ được phân tích riêng ở các phần sau. Chúng nằm trong cùng chương trình để kiểm tra một lớp qua nhiều đường gọi, không chỉ qua `add` và `remove` trực tiếp.

### 4.4. Vì sao tăng sau khi thay đổi thành công?

Trong `add(int, E)`, `data.add` có thể từ chối chỉ số sai trước khi sửa dữ liệu. Nếu viết `modCount++` trước lời gọi đó, một thao tác thất bại có thể làm iterator đang hợp lệ bị vô hiệu hóa, dù danh sách không thay đổi.

Tương tự, `remove(int)` chỉ tăng sau khi lấy được phần tử đã xóa. Quy tắc này rõ ràng khi phép cơ bản của lớp lưu trữ hoặc thành công, hoặc từ chối trước khi sửa dữ liệu.

Không mở rộng kết luận đó thành “mọi phép phức hợp ném ngoại lệ thì không thay đổi gì”. Một thao tác hàng loạt có thể thay đổi một phần rồi thất bại. Nếu tự cài đặt một thuật toán như vậy, phải đảm bảo những thay đổi đã thực sự xảy ra được phản ánh vào bộ đếm; hoặc thiết kế rõ tính nguyên vẹn của thao tác trước khi bắt đầu sửa dữ liệu. Bộ đếm không tự cung cấp khả năng hoàn tác.

### 4.5. Không tăng hai lần trên cùng một đường gọi

Nếu `add(E)` gọi tiếp `add(size(), E)`, không tăng thêm lần nữa chỉ vì cả hai phương thức đều mang tên `add`. Hãy xác định nơi sở hữu lần thay đổi dữ liệu thực tế.

Tương tự, nếu `remove(Object)` kế thừa sử dụng iterator rồi iterator gọi `remove(int)`, trách nhiệm tăng đã được thực hiện ở `remove(int)`. Thêm một phép tăng ở lớp bao ngoài có thể làm chính sách mất nhất quán.

Khi tối ưu một phương thức bằng cách truy cập trực tiếp kho lưu trữ, hãy kiểm tra lại đường đi. Việc trước đây bộ đếm được cập nhật gián tiếp qua iterator không đảm bảo phiên bản tối ưu vẫn đi qua đường đó.


## 5. Ba lỗi thiết kế mà bộ đếm cần giúp phân biệt

Chương trình tiếp theo cố ý xây dựng những biến thể sai so với mục tiêu **danh sách thay đổi được, thay thế giá trị không phá cấu trúc, iterator có cơ chế phát hiện thay đổi cấu trúc ngoài nó**.

`countStructural` và `countReplacement` chỉ là hai công tắc phục vụ thí nghiệm. Một lớp thực tế không nên cung cấp công tắc để lúc bật lúc tắt hợp đồng iterator như thế này.

### 5.1. Chương trình đầy đủ

Lưu vào tệp `CounterDefectsDemo.java`.

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CounterDefectsDemo {
    static final class BrokenList<E> extends AbstractList<E> {
        private final ArrayList<E> data;
        private final boolean countStructural;
        private final boolean countReplacement;

        BrokenList(List<E> initial, boolean countStructural,
                   boolean countReplacement) {
            data = new ArrayList<>(initial);
            this.countStructural = countStructural;
            this.countReplacement = countReplacement;
        }

        @Override
        public E get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public E set(int index, E element) {
            E old = data.set(index, element);
            if (countReplacement) {
                modCount++;
            }
            return old;
        }

        @Override
        public void add(int index, E element) {
            data.add(index, element);
            if (countStructural) {
                modCount++;
            }
        }

        @Override
        public E remove(int index) {
            E old = data.remove(index);
            if (countStructural) {
                modCount++;
            }
            return old;
        }
    }

    public static void main(String[] args) {
        BrokenList<String> missing =
                new BrokenList<>(List.of("A", "B", "C"), false, false);
        Iterator<String> stale = missing.iterator();
        System.out.println("missing-first=" + stale.next());
        missing.remove(0);
        System.out.println("missing-current=" + missing);
        System.out.println("missing-next=" + stale.next());

        BrokenList<String> tooEager =
                new BrokenList<>(List.of("A", "B"), true, true);
        Iterator<String> reader = tooEager.iterator();
        tooEager.set(1, "B2");
        try {
            reader.next();
            throw new AssertionError("Expected false positive");
        } catch (ConcurrentModificationException ex) {
            System.out.println("replacement=CME");
        }

        BrokenList<String> sameSize =
                new BrokenList<>(List.of("A", "B"), true, false);
        Iterator<String> old = sameSize.iterator();
        int savedSize = sameSize.size();
        sameSize.remove(0);
        sameSize.add(0, "X");
        System.out.println("same-size=" + (savedSize == sameSize.size()));
        try {
            old.next();
            throw new AssertionError("Expected CME");
        } catch (ConcurrentModificationException ex) {
            System.out.println("same-size-history=CME");
        }

        BrokenList<String> boundary =
                new BrokenList<>(List.of("A", "B"), true, false);
        Iterator<String> cursor = boundary.iterator();
        System.out.println("boundary-first=" + cursor.next());
        boundary.remove(0);
        System.out.println("boundary-hasNext=" + cursor.hasNext());
        System.out.println("boundary-current=" + boundary);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CounterDefectsDemo.java
java CounterDefectsDemo
```

Stdout:

```text
missing-first=A
missing-current=[B, C]
missing-next=C
replacement=CME
same-size=true
same-size-history=CME
boundary-first=A
boundary-hasNext=false
boundary-current=[B]
```

### 5.2. Bỏ quên cập nhật bộ đếm: không báo lỗi nhưng duyệt sai giả định

Biến thể `missing` xóa dữ liệu thật nhưng không tăng `modCount`. Iterator đã đọc `A`, sau đó danh sách thành `[B, C]`. Lần đọc kế tiếp trả về `C`.

Vì lớp này kế thừa iterator dựa trên chỉ số, con trỏ tiếp tục từ chỉ số `1`. Không có thông tin nào báo cho iterator rằng phần tử ở chỉ số `0` vừa bị xóa. Trong chính thí nghiệm này, hậu quả quan sát được là `B` bị bỏ qua.

Đừng sửa bằng cách bắt ngoại lệ rồi bỏ qua, vì ở đây không có ngoại lệ để bắt. Cần sửa đường thay đổi cấu trúc đang bỏ quên bộ đếm. Đồng thời, dùng mã ứng dụng đúng hợp đồng: nếu muốn xóa trong quá trình duyệt, sử dụng thao tác được iterator hỗ trợ hoặc tổ chức hai giai đoạn duyệt rồi cập nhật.

Sự thiếu vắng bộ đếm chỉ là lỗi khi nó trái với cơ chế và chính sách đã chọn. `AbstractList` cho phép lớp con không sử dụng cơ chế fail-fast; không được từ ví dụ này suy ra mọi collection bắt buộc phải có một trường mang tên `modCount`.

### 5.3. Đếm cả thay thế giá trị: báo lỗi không đúng với chính sách mong muốn

Biến thể `tooEager` tăng bộ đếm trong `set`. Nó không thay đổi số vị trí nhưng vẫn khiến iterator báo lỗi ngay khi đọc.

Nếu lớp được thiết kế với chính sách thay thế giá trị thông thường như `TrackedList`, đây là báo động giả do chính cách ghi nhận của lớp tạo ra. Người viết đã làm bộ đếm mang nghĩa “có phương thức sửa dữ liệu được gọi”, trong khi iterator đang dùng nó như dấu hiệu “giả định về cấu trúc đã hết hiệu lực”.

Một collection khác có thể công bố chính sách duyệt nghiêm ngặt hơn, nhưng chính sách đó phải được thiết kế và diễn giải rõ. Không thay nghĩa của trường chỉ để tăng số trường hợp ném ngoại lệ.

### 5.4. Kiểm tra kích thước: bỏ sót lịch sử xóa rồi chèn

Biến thể `sameSize` xóa `A`, sau đó chèn `X`. Kết quả `same-size=true` xác nhận phép so sánh kích thước không thấy khác biệt giữa trước và sau.

Bộ đếm của biến thể này tăng ở cả hai phép thay đổi cấu trúc. Iterator cũ vẫn nhận ra có thay đổi và báo lỗi. Điều cần phát hiện là giả định của quá trình duyệt đã bị tác động, không phải danh sách cuối cùng có nhiều phần tử hơn hay ít phần tử hơn.

Đây cũng là lý do không đặt `modCount = size()`. Hai đại lượng biểu diễn hai ý nghĩa khác nhau. Không đặt lại bộ đếm về `0` khi `clear()` chỉ vì danh sách lúc đó có kích thước bằng `0`.

### 5.5. hasNext trả về bình thường không phải giấy chứng nhận iterator còn hợp lệ

Phần `boundary` đọc `A`, rồi xóa phần tử đầu bằng danh sách. Iterator đang có con trỏ bằng `1`; danh sách mới cũng có kích thước bằng `1`. `hasNext()` trả về `false`, nên một vòng lặp chỉ tiếp tục khi nó trả `true` sẽ kết thúc mà không đi tới bước đọc tiếp.

Kết quả này được kiểm chứng với iterator kế thừa từ `AbstractList` trên Java 17 đang chạy thí nghiệm. Nó phù hợp với mã OpenJDK 17, nơi `hasNext()` của iterator đó so sánh con trỏ với kích thước mà không kiểm tra bộ đếm ở bước này. Không biến chi tiết cài đặt đó thành quy tắc cho tất cả các iterator. [Mã iterator trong AbstractList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java)

Vì vậy, không viết quy trình “gọi `hasNext()`; nếu chưa lỗi thì cứ sửa danh sách rồi dùng tiếp iterator”. Điều cần làm là tránh vi phạm chính sách duyệt ngay từ thiết kế, thay vì chờ một lời gọi cụ thể bắt lỗi thay mình.

## 6. Theo dõi mọi đường thay đổi, kể cả phương thức kế thừa

### 6.1. Một API công khai có thể đi qua nhiều lớp

Ở `TrackedList`, chỉ ghi đè các phép cơ bản đã đủ để một số phương thức kế thừa hoạt động thông qua chúng. Ví dụ trong chương trình:

```text
addAll
  → thêm từng phần tử
  → add(int, E) của TrackedList
  → sửa data
  → tăng modCount

subList(...).clear()
  → đường xóa khoảng kế thừa
  → iterator xóa từng phần tử trong khoảng
  → remove(int) của TrackedList
  → sửa data
  → tăng modCount
```

Sơ đồ mô tả đường chạy đang được sử dụng trong lớp ví dụ và được kiểm tra bằng stdout. Khi ghi đè thêm phương thức để tăng hiệu năng, đường chạy có thể thay đổi.

Tài liệu `AbstractCollection` mô tả nhiều phương thức mặc định dựa trên `iterator()`, `add` và `Iterator.remove()`. Vì vậy, tự cài đặt iterator không chỉ tác động vòng lặp `for`; nó còn ảnh hưởng những phép kế thừa sử dụng iterator bên trong. [AbstractCollection trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

### 6.2. Phép hàng loạt không nhất thiết tăng bằng số phần tử đầu vào

Ở chương trình đầu:

```text
batch=[1, 4]
batch-revision-delta=2
```

Hai phần tử `2` và `3` đã được xóa qua hai phép xóa cơ bản, nên chênh lệch bằng `2`. Đây là kết quả của lớp ví dụ, không phải yêu cầu rằng mọi `clear`, `removeAll` hoặc `addAll` phải tăng bộ đếm đúng bằng số phần tử bị tác động.

Nếu một lớp khác xóa cả khoảng bằng một thuật toán trực tiếp trên kho lưu trữ, nó có thể ghi nhận thay đổi theo đơn vị thao tác khác. Cần giữ cơ chế phát hiện nhất quán, tôn trọng hợp đồng lớp cha và không bỏ qua các thay đổi mà iterator cũ phải coi là không còn hợp lệ.

Khi thiết kế phương thức hàng loạt, xác định một trong các đường rõ ràng:

- **Gọi các phép cơ bản đã cập nhật bộ đếm:** không bổ sung một lần tăng chung chỉ vì phương thức bao ngoài cũng là phương thức thay đổi.
- **Sửa kho lưu trữ trực tiếp:** phương thức trực tiếp đó chịu trách nhiệm phản ánh các thay đổi vào cơ chế kiểm tra.

Không trộn hai đường một cách vô tình. Nếu phương thức thực hiện được một phần rồi thất bại, xem xét trạng thái còn lại và iterator hiện có, thay vì chỉ kiểm tra trường hợp thành công hoàn toàn.

### 6.3. No-op cần được hiểu theo lớp cụ thể

Trong `TrackedList`, xóa khoảng rỗng không gọi phép xóa cơ bản, nên kết quả là:

```text
empty-range-keeps-revision=true
```

Đây là một đặc điểm kiểm chứng được của lớp đang xây dựng. Không lấy nó làm khẳng định về mọi thao tác “trông như không làm gì” trên mọi collection.

Một thao tác không làm đổi `size()` vẫn có thể ảnh hưởng giả định của iterator. Ngược lại, một lời gọi không tìm thấy phần tử để xóa có thể chỉ đọc dữ liệu và trả `false`. Phải đọc hợp đồng và lần theo đường thực thi cụ thể trước khi quyết định nó thuộc trường hợp nào.

### 6.4. Những đường dễ bỏ sót trong lớp tùy chỉnh

Khi bổ sung tính năng, rà soát theo khả năng sửa kho lưu trữ:

| Đường vào | Điều cần kiểm tra trong chính lớp đang viết |
| --- | --- |
| `add`, `remove` cơ bản | Thay đổi thành công được ghi nhận đúng một lần ở nơi sở hữu |
| `clear`, xóa khoảng | Có đi qua phép xóa cơ bản hay tự sửa dữ liệu trực tiếp? |
| `addAll`, `removeAll`, `retainAll` | Nhánh tối ưu có còn cập nhật cơ chế kiểm tra? |
| `removeIf` | Có dùng iterator đúng hợp đồng, và xử lý thế nào nếu điều kiện ném ngoại lệ? |
| Iterator tự xóa/chèn | Cập nhật cả dữ liệu, vị trí và kỳ vọng riêng của iterator |
| Khung nhìn có thể thay đổi | Thay đổi được chuyển đúng về cấu trúc gốc |
| Mã truy cập kho lưu trữ trực tiếp | Có đường nào vượt qua toàn bộ cơ chế theo dõi? |

Không cần ghi đè mọi phương thức trong bảng. Điều cần chứng minh là những phương thức lớp cho phép đều đi qua đường phù hợp. Kế thừa đúng có thể đơn giản và đáng tin hơn một tập lớn các bản ghi đè gần giống nhau.

## 7. subList: cùng dữ liệu nền, nhiều trạng thái quan sát

`subList` là khung nhìn của một phần danh sách, không phải một danh sách sao chép độc lập. Những thay thế giá trị không làm thay đổi cấu trúc được phản ánh giữa hai phía. Hợp đồng `List` quy định rằng ngữ nghĩa của khung nhìn trở nên không xác định nếu danh sách nền bị thay đổi cấu trúc qua đường khác với chính khung nhìn đó. [List.subList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

Phần khung nhìn của `TrackedListDemo` thể hiện ba tình huống tách biệt.

### 7.1. Thay giá trị qua danh sách gốc

Sau khi tạo `view = list.subList(1, 3)`, chương trình gọi `list.set(1, 222)`. Giá trị đầu của khung nhìn đổi thành `222`:

```text
view-after-set=[222, 30]
```

Lớp ví dụ không coi `set` là thay đổi cấu trúc. Iterator và khung nhìn không phải ảnh chụp của giá trị cũ; chúng vẫn truy cập dữ liệu nền.

### 7.2. Xóa qua chính khung nhìn

Chương trình gọi `view.remove(0)`. Kết quả:

```text
view-after-own-remove=[30]
root-after-view-remove=[201, 30, 40]
```

Thao tác được chuyển về danh sách gốc với vị trí phù hợp; trạng thái của chính khung nhìn được cập nhật qua đường mà nó hỗ trợ. Danh sách gốc và khung nhìn tiếp tục nhất quán với lần xóa này.

Điều đó không có nghĩa mọi iterator được tạo từ trước đều còn hợp lệ. Nếu đã có một iterator riêng trên dữ liệu nền, lần xóa qua khung nhìn vẫn là thay đổi bên ngoài iterator đó.

### 7.3. Thêm qua danh sách gốc rồi dùng lại khung nhìn cũ

Sau `list.add(50)`, chương trình thử `view.size()` và quan sát `old-view=CME`. Đây là cơ chế phát hiện của khung nhìn được kế thừa trong thí nghiệm.

Không suy diễn từ kết quả này rằng mọi lớp triển khai `List` bắt buộc phải báo cùng ngoại lệ tại cùng phương thức sau khi người dùng đã vi phạm điều kiện sử dụng khung nhìn. Cũng không tiếp tục sử dụng khung nhìn cũ sau khi bắt lỗi. Hãy tổ chức các thay đổi qua đường hợp lệ, hoặc tạo lại khung nhìn từ danh sách đã cập nhật khi bắt đầu một công việc mới.

Nếu cần một danh sách độc lập để duyệt trong lúc danh sách gốc thay đổi về sau, việc sao chép cần được lựa chọn có chủ đích. Sao chép không tự làm các đối tượng phần tử bất biến, và việc tạo bản sao trong môi trường có ghi đồng thời vẫn cần chính sách truy cập an toàn.


## 8. Khi không kế thừa iterator của AbstractList

### 8.1. Một trường mang tên modCount không tự tạo cơ chế kiểm tra

`AbstractCollection` yêu cầu lớp con cung cấp iterator và kích thước để hình thành một collection tối thiểu. Nó không cung cấp sẵn trường `modCount` cùng iterator như `AbstractList`. Nếu chọn một cơ chế phát hiện thay đổi bằng bộ đếm, người viết phải kết nối bộ đếm đó với iterator của mình. [AbstractCollection trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

Chương trình dưới đây xây dựng một collection nhỏ cho phép trùng phần tử. Nó không phải `Set` và không có API truy cập theo chỉ số ở bên ngoài. Dữ liệu được lưu trong một `ArrayList` riêng; iterator tự cài đặt đọc dữ liệu theo chỉ số và dùng `structureVersion` của lớp ngoài.

Tên `structureVersion` được dùng có chủ đích: đây là trường do lớp này định nghĩa, không phải trường kế thừa từ `AbstractList`. Cơ chế vẫn có hai vế là phiên bản hiện tại và phiên bản kỳ vọng riêng của iterator.

### 8.2. Chương trình đầy đủ

Lưu vào tệp `ExplicitIteratorDemo.java`.

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class ExplicitIteratorDemo {
    static final class VersionedBag<E> extends AbstractCollection<E> {
        private final ArrayList<E> data = new ArrayList<>();
        private int structureVersion;

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E value) {
            data.add(value);
            structureVersion++;
            return true;
        }

        private void removeAt(int index) {
            data.remove(index);
            structureVersion++;
        }

        @Override
        public Iterator<E> iterator() {
            return new Iterator<E>() {
                private int cursor;
                private int lastReturned = -1;
                private int expectedVersion = structureVersion;

                private void checkVersion() {
                    if (structureVersion != expectedVersion) {
                        throw new ConcurrentModificationException();
                    }
                }

                @Override
                public boolean hasNext() {
                    checkVersion();
                    return cursor < data.size();
                }

                @Override
                public E next() {
                    checkVersion();
                    if (cursor >= data.size()) {
                        throw new NoSuchElementException();
                    }
                    E value = data.get(cursor);
                    lastReturned = cursor;
                    cursor++;
                    return value;
                }

                @Override
                public void remove() {
                    checkVersion();
                    if (lastReturned < 0) {
                        throw new IllegalStateException();
                    }
                    removeAt(lastReturned);
                    cursor = lastReturned;
                    lastReturned = -1;
                    expectedVersion = structureVersion;
                }
            };
        }
    }

    public static void main(String[] args) {
        VersionedBag<String> bag = new VersionedBag<>();
        bag.addAll(List.of("A", "B", "C"));
        Iterator<String> it = bag.iterator();
        System.out.println("first=" + it.next());
        it.remove();
        System.out.println("after-remove=" + bag);
        try {
            it.remove();
        } catch (IllegalStateException ex) {
            System.out.println("double-remove=IllegalStateException");
        }
        System.out.println("continues=" + it.next());

        Iterator<String> stale = bag.iterator();
        bag.add("D");
        try {
            stale.hasNext();
            throw new AssertionError("Expected CME");
        } catch (ConcurrentModificationException ex) {
            System.out.println("custom-hasNext=CME");
        }

        System.out.println("remove-B=" + bag.remove("B"));
        System.out.println("after-inherited-remove=" + bag);
        System.out.println("remove-missing=" + bag.remove("missing"));
        bag.clear();
        System.out.println("after-inherited-clear=" + bag);
        Iterator<String> empty = bag.iterator();
        System.out.println("empty-hasNext=" + empty.hasNext());
        try {
            empty.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty-next=NoSuchElementException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ExplicitIteratorDemo.java
java ExplicitIteratorDemo
```

Stdout:

```text
first=A
after-remove=[B, C]
double-remove=IllegalStateException
continues=B
custom-hasNext=CME
remove-B=true
after-inherited-remove=[C, D]
remove-missing=false
after-inherited-clear=[]
empty-hasNext=false
empty-next=NoSuchElementException
```

### 8.3. Các bất biến cần giữ khi tự viết iterator

Trong chương trình này, ba trường riêng của iterator phối hợp với nhau:

| Trường | Ý nghĩa trong VersionedBag |
| --- | --- |
| `cursor` | Chỉ số sẽ đọc ở lần `next()` kế tiếp |
| `lastReturned` | Vị trí phần tử vừa trả về và còn được phép xóa; `-1` nghĩa là chưa có |
| `expectedVersion` | Phiên bản cấu trúc mà iterator hiện tại chấp nhận |

Sau khi `next()` trả về một phần tử, `cursor` tăng lên. Khi iterator xóa phần tử đó, những phần tử phía sau dồn trái, nên chương trình đưa `cursor` về vị trí vừa xóa. Nếu quên bước này, phần tử kế tiếp có thể bị bỏ qua.

Sau lần xóa hợp lệ:

1. Collection tăng `structureVersion` trong `removeAt`.
2. Iterator điều chỉnh vị trí đọc.
3. Iterator đặt lại `lastReturned` để chặn xóa lặp cùng một kết quả.
4. Iterator nhận phiên bản mới vào `expectedVersion`.

Chỉ thay đổi bước cuối mà không sửa con trỏ có thể làm iterator “không báo lỗi” nhưng vẫn đọc sai. Chỉ sửa con trỏ mà không nhận phiên bản mới lại làm iterator báo lỗi vì chính lần xóa hợp lệ của nó.

Quy tắc `remove()` chỉ được gọi sau một lần `next()` hợp lệ và không được gọi lặp cho cùng kết quả thuộc hợp đồng iterator. `next()` khi hết phần tử phải báo `NoSuchElementException`; đây không phải tình huống thay đổi cấu trúc. [Iterator trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html)

### 8.4. Kiểm tra ở hasNext là lựa chọn của lớp này

`VersionedBag` chủ động gọi `checkVersion()` trong cả `hasNext()`, `next()` và `remove()`. Vì vậy, `stale.hasNext()` báo lỗi sau khi collection được thêm phần tử.

So sánh với thí nghiệm `boundary` ở phần trước cho thấy không nên học thuộc một điểm ném ngoại lệ cố định cho toàn bộ Java Collections Framework. Tự cài đặt iterator nghĩa là phải chọn rõ các điểm kiểm tra và đáp ứng hợp đồng đã công bố.

Việc thêm một điểm kiểm tra có thể giúp phát hiện một số cách sử dụng sai sớm hơn. Nó không tạo một vùng thực thi nguyên tử bao quanh toàn bộ thao tác đọc.

### 8.5. remove và clear kế thừa cũng dùng iterator này

`bag.remove("B")` trả về `true` rồi dữ liệu còn `[C, D]`. `bag.clear()` xóa hết phần tử. Trong chương trình, cả hai hoạt động đúng dù lớp không ghi đè các phương thức đó: đường thực thi kế thừa sử dụng iterator có hỗ trợ xóa.

Ví dụ này kiểm tra nhiều hơn một lời gọi `Iterator.remove()` riêng lẻ. Nó cho thấy cài đặt iterator là một phần nền tảng của các phép collection kế thừa.

Dẫu vậy, đây vẫn là lớp minh họa nhỏ: chưa có cam kết dùng đồng thời, chưa phân tích hiệu năng xóa hàng loạt và chưa xây dựng tập kiểm thử đầy đủ cho một thư viện. Không diễn giải một lần chạy thành bằng chứng về mọi hợp đồng mà một collection công khai cần đáp ứng.

## 9. Chọn fail-fast khi nào là phù hợp?

### 9.1. Khi lớp có cấu trúc thay đổi và muốn phát hiện iterator bị lỗi thời

Fail-fast hữu ích khi thao tác chèn/xóa làm vị trí duyệt cũ không còn đáng tin, người dùng được yêu cầu không thay đổi cấu trúc qua đường ngoài iterator, và báo lỗi sớm giúp tìm ra cách sử dụng sai.

Với lớp `TrackedList`, tận dụng iterator của `AbstractList` cùng `modCount` là cách tự nhiên. Với `VersionedBag`, iterator được viết riêng nên bộ đếm và các điểm kiểm tra cũng phải được nối riêng.

Điểm quyết định là **chính sách duyệt và cấu trúc dữ liệu**, không phải tên trường. Đổi `structureVersion` thành `modCount` trong chương trình thứ ba không làm nó tự động trở thành một lớp kế thừa `AbstractList`.

### 9.2. Không áp đặt cùng cơ chế cho mọi kiểu collection

Một số lựa chọn có mục tiêu khác nhau:

| Chính sách hoặc cấu trúc | Điều người viết cần quyết định |
| --- | --- |
| Duyệt trực tiếp dữ liệu thay đổi được, có quy tắc cấm thay đổi ngoài iterator | Có thể dùng bộ đếm để phát hiện vi phạm |
| Dữ liệu thực sự không thay đổi cấu trúc sau khi tạo | Không thêm bộ đếm chỉ để có một trường cùng tên |
| Iterator duyệt bản sao nội dung tại thời điểm tạo | Thay đổi của nguồn về sau được xử lý theo hợp đồng ảnh chụp |
| Collection dùng đồng thời với iterator có tính nhất quán yếu | Tuân theo chính sách quan sát của cấu trúc đồng thời đó |
| Lớp bao hoặc khung nhìn của một collection khác | Xác định dữ liệu nào được dùng chung và cơ chế nào chịu trách nhiệm phát hiện |

Ví dụ, iterator của `CopyOnWriteArrayList` dùng ảnh chụp mảng và không báo `ConcurrentModificationException`; các thao tác thay đổi qua iterator đó không được hỗ trợ. Đây là lựa chọn thiết kế của lớp này, không phải một bản fail-fast bị thiếu bộ đếm. [CopyOnWriteArrayList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Iterator của `ConcurrentHashMap` có thể phản ánh trạng thái ở những thời điểm khác nhau trong quá trình quan sát và không báo `ConcurrentModificationException`. Không thay chính sách đó bằng cơ chế iterator thông thường chỉ vì cũng đang viết một collection. [ConcurrentHashMap trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Một khung nhìn không cho phép sửa qua chính nó cũng chưa chắc là dữ liệu bất biến: cấu trúc gốc có thể vẫn được sửa qua tham chiếu khác. Khi chọn cơ chế kiểm tra, phải nhìn vào toàn bộ đường sở hữu và chia sẻ dữ liệu.

### 9.3. Với Map và Set tùy chỉnh, bắt đầu từ chính sách của cấu trúc đó

`AbstractMap` không cung cấp sẵn cơ chế `modCount` như `AbstractList`. Các phương thức của nó được xây dựng quanh `entrySet`; iterator và khả năng xóa qua iterator của tập entry là một phần quan trọng khi cài đặt map thay đổi được. [AbstractMap trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html)

`AbstractSet` kế thừa nền tảng từ `AbstractCollection` và bổ sung các yêu cầu của tập hợp; không vì kế thừa nó mà tự nhận được toàn bộ iterator fail-fast. [AbstractSet trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html)

Nếu xây dựng map với cơ chế kiểm tra riêng, cần xem cả các khung nhìn khóa, giá trị và entry. Một thay đổi làm iterator của cấu trúc gốc lỗi thời có thể được thực hiện qua khung nhìn; đó vẫn là đường phải được quản lý.

Với tập hợp, thử thêm một phần tử vốn đã có không đồng nghĩa chắc chắn phát sinh một lần chèn. Với map, cập nhật giá trị của khóa đã có cũng cần được phân biệt với tạo ánh xạ mới theo hợp đồng đang chọn. Không sao chép máy móc bảng của danh sách sang mọi cấu trúc.

## 10. modCount không làm collection an toàn khi dùng đồng thời

`ConcurrentModificationException` có thể xuất hiện trong một luồng. Tên ngoại lệ không chứng minh có hai luồng chạy cùng lúc. Các chương trình của bài cố ý dùng thứ tự gọi tuần tự để kiểm tra được chính xác nguyên nhân và stdout.

Ở chiều ngược lại, khi có các luồng sửa dữ liệu mà không có cơ chế phối hợp phù hợp, fail-fast chỉ phát hiện theo nỗ lực tốt nhất. Tài liệu ngoại lệ yêu cầu không dựa vào việc nó chắc chắn được ném để làm nền tảng cho tính đúng của chương trình. [ConcurrentModificationException trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html)

Một phép so sánh bộ đếm không:

- Khóa cấu trúc đang được đọc.
- Làm toàn bộ quá trình kiểm tra rồi lấy phần tử trở thành một thao tác nguyên tử.
- Tự bảo đảm các trường dữ liệu được nhìn thấy nhất quán giữa các luồng.
- Hoàn tác phần thay đổi đã xảy ra trước khi báo lỗi.

Trong `VersionedBag`, một luồng khác vẫn có thể sửa dữ liệu giữa `checkVersion()` và `data.get(cursor)` nếu chương trình cho phép truy cập như vậy. Thêm kiểm tra vào nhiều vị trí không loại bỏ được vấn đề thiết kế truy cập đồng thời.

Đổi riêng bộ đếm sang `volatile`, `AtomicInteger` hoặc một kiểu số lớn hơn cũng không biến toàn bộ collection thành cấu trúc an toàn cho nhiều luồng. Các thao tác trên kho dữ liệu, con trỏ và quan hệ giữa nhiều bước vẫn cần một chính sách phối hợp chung.

Những cách tổ chức phù hợp có thể là giới hạn collection trong một luồng, dùng khóa theo một giao thức nhất quán, duyệt bản sao được tạo an toàn, hoặc chọn cấu trúc trong `java.util.concurrent` có hợp đồng thích hợp. Nếu dùng lớp bao đồng bộ từ `Collections`, tài liệu còn yêu cầu đồng bộ thủ công quanh quá trình duyệt theo đúng đối tượng khóa được chỉ định; đồng bộ từng lời gọi riêng lẻ không tự bao trùm cả vòng lặp. [Collections.synchronizedList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

Cũng không dùng vòng lặp “gặp `ConcurrentModificationException` thì thử lại cho đến khi hết lỗi” như một cơ chế phối hợp. Công việc đã làm trước lúc lỗi có thể bị lặp lại, dữ liệu có thể tiếp tục đổi, và không có giới hạn bảo đảm sẽ thành công. Sửa cách sở hữu, thay đổi và duyệt dữ liệu trước.

## 11. Kiểm chứng một cài đặt thay vì chỉ đợi thấy ngoại lệ

### 11.1. Những nhóm tình huống cần thử

Khi viết collection có cơ chế này, kiểm tra từng nhóm riêng:

1. **Duyệt bình thường:** đúng thứ tự hoặc đúng tập phần tử theo hợp đồng; hết dữ liệu thì `next()` báo đúng ngoại lệ.
2. **Thay đổi ngoài iterator:** thử thêm, xóa và xóa rồi thêm để khôi phục kích thước; kiểm tra tại những điểm mà lớp hứa phát hiện.
3. **Thay đổi qua iterator:** xóa hợp lệ phải cho phép iterator đó tiếp tục, đồng thời điều chỉnh con trỏ đúng.
4. **Trạng thái thao tác iterator:** xóa trước `next()`, xóa hai lần cho cùng kết quả và tiếp tục sau khi hết dữ liệu.
5. **Nhiều iterator và khung nhìn:** thay đổi qua một đường có làm các đối tượng quan sát khác nhận ra trạng thái cũ?
6. **Nhánh không thay đổi hoặc thất bại:** phần tử không tồn tại, khoảng rỗng, chỉ số sai; kết quả phải phù hợp chính sách của lớp.
7. **Phương thức hàng loạt và phiên bản tối ưu:** không bỏ qua bộ đếm, không tăng trùng, không che giấu phần thay đổi đã xảy ra nếu thao tác thất bại giữa chừng.

Đừng coi số lần nhìn thấy `ConcurrentModificationException` là thước đo chất lượng. Một iterator báo lỗi với cả những thao tác mà lớp công bố là hợp lệ cũng có thể được cài đặt sai.

Ba chương trình trong bài kiểm chứng một phần các nhóm trên bằng thao tác tuần tự. Chúng không kiểm tra tranh chấp luồng và không được dùng để kết luận collection an toàn khi dùng đồng thời.

### 11.2. Bài tập áp dụng và gợi ý tự kiểm tra

**Bài 1 — xóa qua hai đường.** Trong `TrackedListDemo`, tạo iterator rồi gọi `list.remove(Integer.valueOf(30))`. Sau đó tạo lại tình huống tương đương nhưng dùng chính `iterator.remove()` sau khi iterator trả về `30`. Hai đường có ý nghĩa khác nhau với iterator nào?

Gợi ý: phương thức `remove(Object)` có thể dùng một iterator nội bộ riêng. Điều đó không làm nó trở thành phép xóa của iterator mà mã ứng dụng đang giữ.

**Bài 2 — lỗi cập nhật bộ đếm.** Bỏ dòng `modCount++` trong `TrackedList.remove(int)`, giữ nguyên trong `add`. Chỉ kiểm tra thêm ngoài iterator có phát hiện được lỗi này không?

Gợi ý: không. Cần kiểm tra từng đường xóa, kể cả xóa qua khung nhìn và các phép kế thừa. Một đường được cập nhật đúng không đại diện cho đường khác.

**Bài 3 — sửa iterator tự cài đặt.** Trong `VersionedBag`, bỏ bước `cursor = lastReturned`, giữ nguyên việc cập nhật phiên bản kỳ vọng. Sau khi đọc rồi xóa `A` khỏi `[A, B, C]`, phần tử đọc kế tiếp là gì?

Gợi ý: con trỏ vẫn ở chỉ số `1`, dữ liệu đã thành `[B, C]`, nên lần đọc kế tiếp có thể bỏ qua `B` và trả về `C`. Bộ đếm đúng không thay thế được logic con trỏ đúng.

**Bài 4 — đếm không đồng nghĩa an toàn.** Nếu thay `structureVersion` bằng `AtomicInteger` và dùng phép tăng nguyên tử, những bước nào của `next()` và `remove()` vẫn chưa được bảo vệ như một thao tác thống nhất?

Gợi ý: kiểm tra phiên bản, kiểm tra giới hạn, truy cập kho dữ liệu, sửa dữ liệu và cập nhật vị trí vẫn là nhiều bước liên quan. Phải thiết kế giao thức truy cập toàn bộ cấu trúc.

**Bài 5 — tối ưu xóa khoảng.** Nếu ghi đè đường xóa khoảng để dịch chuyển dữ liệu một lần thay vì xóa từng phần tử, những kiểm tra nào cần giữ?

Gợi ý: kiểm tra giới hạn trước khi sửa, cập nhật kho lưu trữ và kích thước đúng, phản ánh thay đổi vào cơ chế phát hiện, không tăng trùng với đường xóa cơ bản, và kiểm tra cả khung nhìn lẫn iterator được tạo trước thao tác. Không dùng stdout chênh lệch bằng `2` của phiên bản cũ làm yêu cầu cho mọi thuật toán mới.

### 11.3. Các điều cần nắm sau bài học

`modCount` hữu ích khi nó gắn với một chính sách duyệt được xác định và mọi đường thay đổi cấu trúc đều tuân theo chính sách đó. Iterator phải giữ kỳ vọng riêng, đồng thời quản lý đúng vị trí và quyền thực hiện thao tác.

Khi kế thừa `AbstractList`, cập nhật các phép cơ bản đúng cách giúp tận dụng iterator và các đường thực thi kế thừa. Khi viết iterator riêng, tự chịu trách nhiệm nối tất cả thành phần đó lại. Khi dùng cấu trúc có chính sách ảnh chụp hoặc dùng đồng thời, đọc hợp đồng tương ứng trước khi lựa chọn cơ chế.

Một lần không báo lỗi không chứng minh dữ liệu không thay đổi. Một lần báo lỗi cũng không sửa được cách sử dụng sai. Giá trị của cơ chế nằm ở việc giúp phát hiện một nhóm lỗi, còn tính đúng vẫn đến từ hợp đồng và thiết kế truy cập dữ liệu.
