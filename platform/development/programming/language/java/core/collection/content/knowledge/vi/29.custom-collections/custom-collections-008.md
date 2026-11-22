# Kiểm thử theo hợp đồng thay vì phụ thuộc lớp cài đặt

## Một bài kiểm thử cần bảo vệ lời hứa nào?

Giả sử một hàm nhận `List<String>`. Hôm nay nó được gọi với `ArrayList`, sau này chuyển sang `LinkedList` hoặc một danh sách do bạn tự viết. Nếu hành vi mà hàm cần vẫn được giữ, bài kiểm thử nên tiếp tục đúng.

Một kiểm tra như “đối tượng phải có lớp chính xác là `ArrayList`” thường không bảo vệ nhu cầu đó. Nó khóa vào cách tạo đối tượng. Ngược lại, “phần tử thêm ở vị trí 1 xuất hiện tại vị trí 1, các phần tử sau dịch đúng và kích thước tăng một” mô tả hành vi công khai.

**Kiểm thử theo hợp đồng** là kiểm tra những điều API cam kết, với các điều kiện sử dụng tương ứng. Hợp đồng gồm nhiều thứ hơn dữ liệu cuối:

- Điều kiện đầu vào và trạng thái trước khi gọi.
- Kết quả trả về.
- Dữ liệu nào thay đổi và dữ liệu nào được giữ.
- Ngoại lệ trong từng trường hợp.
- Thứ tự, tính duy nhất, cách so sánh bằng nhau.
- Khả năng cập nhật qua iterator và view.
- Chính sách `null`, thao tác tùy chọn và giới hạn miền dữ liệu.
- Các bảo đảm về đồng thời nếu API thật sự công bố chúng.

Một **chi tiết cài đặt** là cách lớp thực hiện lời hứa: dùng mảng hay nút liên kết, tên trường nội bộ, số ô mảng đang cấp phát, thuật toán tăng dung lượng hoặc đường gọi helper riêng.

Thay đổi chi tiết ấy có thể hợp lệ nếu hợp đồng bên ngoài còn đúng. Một bộ kiểm thử tốt giúp sửa cách cài đặt mà vẫn phát hiện việc phá vỡ hành vi cần giữ.

## Ba nguồn hợp đồng cần phân biệt

| Nguồn lời hứa | Ví dụ | Bộ kiểm thử áp dụng |
| --- | --- | --- |
| Interface | `List.set` trả phần tử cũ; iterator list duyệt theo thứ tự | Nhóm kiểm thử dùng chung cho các triển khai đáp ứng khả năng cần thiết |
| Họ cấu trúc hoặc hồ sơ khả năng | Danh sách kích thước cố định; list cho phép `null`; iterator chỉ đọc | Nhóm kiểm thử có điều kiện theo khả năng đã công bố |
| API công khai riêng của lớp | Queue có dung lượng cụ thể; view có thứ tự cụ thể; iterator snapshot | Nhóm kiểm thử mở rộng dành cho lời hứa đó |

Không phải mọi đặc điểm của một lớp cụ thể đều là chi tiết nội bộ. Nếu lớp công bố thứ tự duyệt hoặc chính sách snapshot, đó là hợp đồng có thể kiểm thử. Mục tiêu là xác định nguồn của từng kỳ vọng, không phải cấm nhắc tên lớp trong mọi bài kiểm thử.

Ví dụ, kiểm thử một thuật toán nhận `Set` không nên tự đòi thứ tự chèn. Nhưng kiểm thử một API công bố giữ thứ tự chèn cần xác nhận thứ tự đó. Hai mục tiêu khác nhau dẫn tới hai kiểu kiểm tra khác nhau.

Với lớp kế thừa `AbstractList` hoặc các lớp khung khác, đừng chỉ kiểm tra những phương thức mới viết. Iterator, view và phương thức mặc định có thể mở các đường hành vi khác. `AbstractList` cung cấp nhiều phần cài đặt trên các phương thức nền; xem [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

## Một vài kỳ vọng dễ khóa nhầm vào cài đặt

| Kỳ vọng dễ sai | Vì sao không là hợp đồng chung | Kỳ vọng phù hợp hơn |
| --- | --- | --- |
| Kết quả phải có `getClass() == ArrayList.class` | Một triển khai khác có thể cung cấp cùng hành vi | Kiểm tra dữ liệu và các khả năng mà bên dùng yêu cầu |
| Mọi `Set` duyệt theo một thứ tự cố định | `Set` không đưa ra một thứ tự duyệt chung | Kiểm tra thành viên/tính duy nhất; thêm kiểm tra thứ tự khi API công bố |
| Iterator của priority queue trả dãy đã sắp | Thứ tự phần tử đầu để lấy khác thứ tự iterator | Kiểm tra thứ tự qua các lần lấy đầu, theo comparator đã chọn |
| Mọi `List` đều thêm, xóa và thay được | Nhiều thao tác là tùy chọn | Xác định hồ sơ khả năng rồi kiểm tra đúng từng thao tác |
| List sửa được thì iterator cũng sửa được | Một iterator snapshot có thể chỉ đọc | Kiểm tra khả năng của iterator riêng |
| Sửa ngoài iterator luôn lập tức gây CME | Phụ thuộc chính sách và điểm kiểm tra | Chỉ kiểm tra bảo đảm đã công bố, không dùng CME làm điều kiện đúng đắn |
| Ngoại lệ phải có đúng câu chữ của JDK đang chạy | Thông điệp thường không là hợp đồng chung | Kiểm tra loại ngoại lệ và trạng thái liên quan |
| Thêm N phần tử xong phải có dung lượng nội bộ M | Đó có thể là chính sách cấp phát riêng | Kiểm tra nội dung, kích thước và khả năng đã hứa |
| Một thao tác phải xong dưới vài mili giây trong mọi lần CI | Chịu ảnh hưởng tải máy và môi trường | Tách kiểm thử hành vi khỏi phép đo hiệu năng có phương pháp |

`HashSet` và `HashMap` không bảo đảm thứ tự duyệt cố định; một kết quả hiển thị lặp lại nhiều lần trên máy hiện tại chưa tạo ra hợp đồng mới. Xem [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) và [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Đối với `PriorityQueue`, lời hứa về phần tử ưu tiên không khiến iterator trở thành phép sắp xếp. Kiểm thử cần chọn đúng thao tác để quan sát tính chất đó; xem [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## Viết kỳ vọng từ tiền điều kiện và hậu điều kiện

Xét `set(index, value)` của một list hỗ trợ thay thế.

Một trường hợp có ý nghĩa:

~~~text
Trước:
    [A, B, A]
    index = 1
    value = X

Sau:
    giá trị trả về = B
    nội dung = [A, X, A]
    kích thước = 3
~~~

Nếu chỉ kiểm tra nội dung cuối, một lớp trả nhầm `X` thay vì `B` vẫn vượt qua. Nếu chỉ kiểm tra giá trị trả về, một lớp không thực sự thay phần tử cũng có thể vượt qua.

Với một lần xóa theo giá trị trên list:

~~~text
Trước:
    [A, B, A]

remove("A"):
    trả true
    còn [B, A]
~~~

Hợp đồng xóa lần xuất hiện đầu tiên làm thứ tự sau thao tác có ý nghĩa. Chỉ đổi kết quả thành set `{A,B}` sẽ làm mất thông tin về vị trí và số lần xuất hiện.

Các hành vi về vị trí, thứ tự, giá trị trả về và phép so sánh list được quy định trong [List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html). Một ca kiểm thử nên giải thích được nó đang bảo vệ phần nào của lời hứa ấy.

### Kiểm tra ngoại lệ cũng có tiền điều kiện

Để kiểm tra `get` ngoài biên, dùng một list hợp lệ và chỉ số không hợp lệ. Để kiểm tra `UnsupportedOperationException` của `set`, dùng một vị trí hợp lệ trên list không hỗ trợ thay thế.

Nếu vừa dùng chỉ số sai vừa yêu cầu thao tác không được hỗ trợ, bài kiểm thử có thể tự đòi một thứ tự ưu tiên ngoại lệ mà API không hứa.

Tương tự, iterator không hỗ trợ `remove` và iterator hỗ trợ nhưng chưa gọi `next` là hai trường hợp khác. Không dùng một lời gọi sai đồng thời nhiều điều kiện để kết luận khả năng của đối tượng.

## Hồ sơ khả năng phải được khai báo rõ

Một bộ kiểm thử dùng chung không có nghĩa áp cùng một thao tác ghi cho mọi đối tượng.

Có thể mô tả một hồ sơ nhỏ như sau:

| Khả năng | Câu hỏi cần trả lời |
| --- | --- |
| Thay đổi kích thước | Có cho thêm/xóa theo các đường đang kiểm tra không? |
| Thay thế phần tử | `set(index,value)` có được hỗ trợ không? |
| Iterator xóa | `Iterator.remove` có được hỗ trợ không? |
| List iterator thay thế | `ListIterator.set` có được hỗ trợ không? |
| Chính sách `null` | Khởi tạo/ghi/đọc `null` có quy tắc gì? |
| View | `subList`, `keySet`, `values` hoặc `entrySet` ghi ngược thế nào? |
| Đồng thời | Cần đồng bộ ngoài, có snapshot hay cho phép cập nhật đồng thời? |

Không dùng một cờ “mutable” để suy ra tất cả. `CopyOnWriteArrayList` cho sửa list nhưng iterator của nó không hỗ trợ `remove/set/add`. Đó là hợp đồng được công bố, không phải lỗi để bộ kiểm thử chung phải từ chối. Xem [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

Hồ sơ phải lấy từ API đã duyệt, không được suy ra bằng cách thử ngẫu nhiên rồi đổi cờ cho tới khi bài kiểm thử xanh. Nếu lớp được yêu cầu hỗ trợ xóa mà xóa đang hỏng, việc đổi cờ thành “không hỗ trợ” chỉ làm mất yêu cầu ban đầu.

Cũng không phải mọi khả năng đều độc lập theo đúng năm cờ của một ví dụ. Một collection chỉ cho xóa qua view, một list hạn chế trùng hoặc một cấu trúc có miền phần tử riêng có thể cần hồ sơ khác. Bộ kiểm thử phải có tiền điều kiện phù hợp với đối tượng của nó.

### Trường hợp không có tác động không đủ để dò khả năng

Một collection không hỗ trợ thêm có thể nhận `addAll` với nguồn rỗng mà không ném ngoại lệ. Một thao tác xóa giá trị không có có thể trả `false` dù xóa giá trị đang có sẽ bị chặn.

Do đó, khi kiểm tra khả năng không được hỗ trợ, chọn đầu vào thật sự cần đường ghi đó, chẳng hạn thêm một phần tử vào vị trí hợp lệ hoặc xóa phần tử đang tồn tại.

Khi kiểm tra một lời gọi không có tác động theo hợp đồng tổng quát, đừng tự ép tất cả triển khai phải có cùng kết quả ngoại lệ. Một lớp cụ thể có thể công bố chính sách mạnh hơn và được kiểm thử riêng. Quy tắc thao tác tùy chọn và các trường hợp không có tác động nằm trong [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## Chuẩn bị dữ liệu và bộ tạo đối tượng

Một bộ tạo đối tượng, thường gọi là `factory` trong mã kiểm thử, nhận dữ liệu đầu vào rồi tạo đối tượng cần thử. Bộ kiểm thử hành vi làm việc qua interface, không cần biết bên trong là mảng hay liên kết.

Ví dụ về ý tưởng:

~~~java
Function<List<String>, List<String>> factory = ArrayList::new;
List<String> actual = factory.apply(List.of("A", "B", "A"));
~~~

Đoạn này minh họa cách truyền bộ tạo; các phần `import` và bộ kiểm thử đầy đủ có ở chương trình phía dưới.

Dữ liệu nên có lý do:

- Collection rỗng kiểm tra biên không có phần tử.
- Một phần tử kiểm tra xóa cuối và chuyển sang rỗng.
- `[A,B,A]` kiểm tra thứ tự cùng hai lần xuất hiện bằng nhau.
- `null` chỉ đưa vào hồ sơ cho phép hoặc ca từ chối rõ ràng.
- Phần tử có cùng hash nhưng không bằng nhau hữu ích khi kiểm tra cấu trúc băm.
- Các đối tượng bằng nhau nhưng khác định danh giúp phát hiện xóa nhầm lần xuất hiện.

Mỗi ca có thay đổi nên dùng một đối tượng mới hoặc khôi phục trạng thái theo giao thức rõ ràng. Một ca kiểm thử không nên phụ thuộc vào việc ca khác đã chạy trước.

Với đối tượng sửa được, các lần tạo cần không vô tình chia sẻ kho có thể bị sửa lẫn nhau. Với đối tượng bất biến, việc bộ tạo có thể dùng lại cùng một đối tượng không tự là lỗi; đừng ép danh tính khác nhau khi hợp đồng chỉ hứa giá trị.

## Chương trình đầy đủ: một bộ kiểm thử, nhiều triển khai

Lưu vào `CollectionContractDemo.java`. Chương trình không cần thư viện kiểm thử ngoài. `Verify` dùng các phép kiểm tra tường minh nên không phụ thuộc việc bật `-ea` cho câu lệnh `assert` của Java.

Phạm vi bộ kiểm thử này là các hồ sơ list đã chọn:

- Bộ tạo nhận danh sách nguồn, giữ thứ tự và các lần xuất hiện, đồng thời tạo được list rỗng.
- Những hồ sơ đánh dấu `resizable` hỗ trợ nhóm thêm/xóa trực tiếp và xóa khoảng qua `subList` được dùng trong bài.
- `replaceable` chỉ nói về `List.set`; khả năng thay/xóa qua iterator được khai báo riêng.
- Chính sách `allowsNull` trong ví dụ bao gồm khởi tạo chứa `null`, đọc/tìm nó và thay bằng `null` nếu hỗ trợ `set`.
- Bộ kiểm thử chạy tuần tự, không xác minh chính sách cập nhật đồng thời.

Đây là một bộ kiểm thử có phạm vi xác định, không phải bộ chứng nhận mọi triển khai `List` có thể có.

`SlotList` là lớp tùy chỉnh giữ số ô cố định, hỗ trợ `get/size/set` và sao chép nguồn vào mảng riêng. `WrongReturnList` cố ý trả phần tử mới từ `set` để kiểm tra chất lượng bộ kiểm thử. Không dùng lớp cố ý sai làm cài đặt cho ứng dụng.

~~~java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Random;
import java.util.function.Function;
import java.util.concurrent.CopyOnWriteArrayList;

public class CollectionContractDemo {
    record Spec(
            String name,
            Function<List<String>, List<String>> factory,
            boolean resizable,
            boolean replaceable,
            boolean iteratorRemovable,
            boolean iteratorReplaceable,
            boolean allowsNull) {
        List<String> fresh(String... values) {
            return factory.apply(Arrays.asList(values));
        }
    }

    static class SlotList extends AbstractList<String> {
        private final String[] data;

        SlotList(List<String> source) {
            data = source.toArray(String[]::new);
        }

        @Override public int size() {
            return data.length;
        }

        @Override public String get(int index) {
            return data[Objects.checkIndex(index, data.length)];
        }

        @Override public String set(int index, String value) {
            Objects.checkIndex(index, data.length);
            String old = data[index];
            data[index] = value;
            return old;
        }
    }

    static final class WrongReturnList extends SlotList {
        WrongReturnList(List<String> source) {
            super(source);
        }

        @Override public String set(int index, String value) {
            super.set(index, value);
            return value;
        }
    }

    static final class ContractFailure extends AssertionError {
        ContractFailure(String message) {
            super(message);
        }
    }

    static final class Verify {
        private int checks;

        void check(boolean condition, String message) {
            checks++;
            if (!condition) {
                throw new ContractFailure(message);
            }
        }

        void equal(Object expected, Object actual, String message) {
            check(Objects.equals(expected, actual), message);
        }

        void throwsType(Class<? extends Throwable> type,
                        Runnable operation, String message) {
            checks++;
            try {
                operation.run();
            } catch (Throwable failure) {
                if (type.isInstance(failure)) {
                    return;
                }
                throw new ContractFailure(message + ": wrong exception "
                        + failure.getClass().getSimpleName());
            }
            throw new ContractFailure(message + ": no exception");
        }
    }

    static int contract(Spec spec) {
        Verify v = new Verify();
        List<String> list = spec.fresh("A", "B", "A");
        List<String> expected = List.of("A", "B", "A");
        v.equal(3, list.size(), "seed size");
        v.check(!list.isEmpty(), "seed must be nonempty");
        v.equal(expected, list, "list order and multiplicity");
        v.check(list.equals(expected) && expected.equals(list), "symmetric equality");
        v.equal(expected.hashCode(), list.hashCode(), "equal lists need equal hashes");
        v.equal("B", list.get(1), "indexed read");
        v.equal(0, list.indexOf("A"), "first equal occurrence");
        v.equal(2, list.lastIndexOf("A"), "last equal occurrence");
        v.check(list.contains("A") && !list.contains("missing"), "membership");
        v.throwsType(IndexOutOfBoundsException.class,
                () -> list.get(-1), "negative read index");
        v.throwsType(IndexOutOfBoundsException.class,
                () -> list.get(list.size()), "read index at size");

        Object[] array = list.toArray();
        v.equal(3, array.length, "array length");
        array[0] = "outside";
        v.equal("A", list.get(0), "array must not write through");
        String[] typed = list.toArray(String[]::new);
        v.check(Arrays.equals(new String[]{"A", "B", "A"}, typed), "typed array contents");

        Iterator<String> iterator = list.iterator();
        v.check(iterator.hasNext() && iterator.hasNext(), "hasNext must not consume");
        v.equal("A", iterator.next(), "first iterator value");
        v.equal("B", iterator.next(), "next without hasNext");
        v.equal("A", iterator.next(), "last iterator value");
        v.check(!iterator.hasNext(), "iterator exhausted");
        v.throwsType(NoSuchElementException.class, iterator::next, "next past end");

        List<String> empty = spec.fresh();
        v.check(empty.isEmpty() && empty.size() == 0, "empty construction");
        v.check(!empty.iterator().hasNext(), "empty iterator");
        v.throwsType(NoSuchElementException.class,
                empty.iterator()::next, "next on empty");

        List<String> forSet = spec.fresh("A", "B", "A");
        if (spec.replaceable()) {
            v.equal("B", forSet.set(1, "X"), "set must return previous value");
            v.equal(List.of("A", "X", "A"), forSet, "set must replace one position");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> forSet.set(1, "X"), "replacement unsupported");
            v.equal(expected, forSet, "rejected replacement must not change list");
        }
        ListIterator<String> listIterator = forSet.listIterator();
        listIterator.next();
        if (spec.iteratorReplaceable()) {
            listIterator.set("Z");
            v.equal(List.of("Z", "X", "A"), forSet, "list iterator set");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> listIterator.set("Z"), "iterator replacement unsupported");
        }

        List<String> forResize = spec.fresh("A", "B", "A");
        if (spec.resizable()) {
            forResize.add(1, "X");
            v.equal(List.of("A", "X", "B", "A"), forResize, "indexed insertion");
            v.check(forResize.add("Y"), "append reports a change");
            v.equal("B", forResize.remove(2), "indexed removal returns removed value");
            v.check(forResize.remove("A"), "remove present value");
            v.equal(List.of("X", "A", "Y"), forResize, "remove first equal occurrence");
            v.check(!forResize.remove("missing"), "missing removal reports false");

            List<String> byView = spec.fresh("A", "B", "A");
            byView.subList(1, 3).clear();
            v.equal(List.of("A"), byView, "subList removal writes through");
            forResize.clear();
            v.check(forResize.isEmpty(), "clear removes all values");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.add(0, "X"), "insertion unsupported");
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.remove(0), "indexed removal unsupported");
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.remove("A"), "value removal unsupported");
            v.equal(expected, forResize, "rejected resize must preserve values");
        }


        List<String> byIterator = spec.fresh("A", "B", "A");
        Iterator<String> removing = byIterator.iterator();
        if (spec.iteratorRemovable()) {
            v.throwsType(IllegalStateException.class,
                    removing::remove, "remove before next");
            removing.next();
            removing.next();
            removing.next();
            removing.remove();
            v.equal(List.of("A", "B"), byIterator, "iterator removes last returned occurrence");
            v.throwsType(IllegalStateException.class,
                    removing::remove, "remove twice");
        } else {
            removing.next();
            v.throwsType(UnsupportedOperationException.class,
                    removing::remove, "iterator removal unsupported");
            v.equal(expected, byIterator, "rejected iterator removal preserves list");
        }

        if (spec.allowsNull()) {
            List<String> nullable = spec.fresh("A", null, "A");
            v.equal(null, nullable.get(1), "null value can be read");
            v.equal(1, nullable.indexOf(null), "null value can be found");
            if (spec.replaceable()) {
                List<String> target = spec.fresh("A");
                v.equal("A", target.set(0, null), "replace with null");
                v.equal(null, target.get(0), "null replacement stored");
            }
        } else {
            v.throwsType(NullPointerException.class,
                    () -> spec.fresh("A", null), "factory rejects null");
        }
        return v.checks;
    }

    static int modelSequence(Spec spec, long seed, int steps) {
        Verify v = new Verify();
        Random random = new Random(seed);
        List<String> actual = spec.fresh();
        List<String> model = new ArrayList<>();
        for (int step = 0; step < steps; step++) {
            int action = random.nextInt(5);
            String value = "v" + random.nextInt(7);
            if (model.isEmpty() || action == 0) {
                int index = random.nextInt(model.size() + 1);
                model.add(index, value);
                actual.add(index, value);
            } else if (action == 1) {
                int index = random.nextInt(model.size());
                v.equal(model.remove(index), actual.remove(index),
                        "model remove result at step " + step);
            } else if (action == 2) {
                int index = random.nextInt(model.size());
                v.equal(model.set(index, value), actual.set(index, value),
                        "model set result at step " + step);
            } else if (action == 3) {
                v.equal(model.remove(value), actual.remove(value),
                        "model value removal at step " + step);
            } else {
                model.clear();
                actual.clear();
            }
            v.equal(model.size(), actual.size(), "model size at step " + step);
            v.equal(model, actual, "model sequence at step " + step);
        }
        return steps;
    }

    public static void main(String[] args) {
        List<Spec> specs = List.of(
                new Spec("ArrayList", ArrayList::new, true, true, true, true, true),
                new Spec("LinkedList", LinkedList::new, true, true, true, true, true),
                new Spec("CopyOnWriteArrayList", CopyOnWriteArrayList::new,
                        true, true, false, false, true),
                new Spec("array-backed fixed list",
                        source -> Arrays.asList(source.toArray(String[]::new)),
                        false, true, false, true, true),
                new Spec("List.copyOf", List::copyOf, false, false, false, false, false),
                new Spec("SlotList", SlotList::new, false, true, false, true, true)
        );

        for (Spec spec : specs) {
            int checks = contract(spec);
            System.out.println(spec.name() + " = PASS (" + checks + " checks)");
        }
        for (Spec spec : specs) {
            if (spec.resizable() && spec.replaceable()) {
                int steps = modelSequence(spec, 2026L, 200);
                System.out.println(spec.name() + " model = PASS (" + steps + " steps)");
            }
        }

        Spec broken = new Spec("WrongReturnList",
                WrongReturnList::new, false, true, false, true, true);
        try {
            contract(broken);
            throw new AssertionError("Broken implementation was not detected");
        } catch (ContractFailure expected) {
            System.out.println("deliberately broken = DETECTED: " + expected.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 CollectionContractDemo.java
java CollectionContractDemo
~~~

Mã đã được biên dịch với `--release 17` và chạy bằng OpenJDK Zulu 24.0.2. Stdout chính xác:

~~~text
ArrayList = PASS (41 checks)
LinkedList = PASS (41 checks)
CopyOnWriteArrayList = PASS (40 checks)
array-backed fixed list = PASS (36 checks)
List.copyOf = PASS (33 checks)
SlotList = PASS (36 checks)
ArrayList model = PASS (200 steps)
LinkedList model = PASS (200 steps)
CopyOnWriteArrayList model = PASS (200 steps)
deliberately broken = DETECTED: set must return previous value
~~~

## Bộ kiểm thử đã kiểm tra điều gì?

### Phần đọc chung giữ nguyên qua các triển khai

Các ca đầu kiểm tra:

- Kích thước, rỗng/không rỗng.
- Thứ tự và số lần xuất hiện.
- `get`, `indexOf`, `lastIndexOf`, `contains`.
- `equals` hai chiều với một list có cùng dữ liệu và tính nhất quán `hashCode`.
- Chỉ số đọc âm và bằng `size`.
- `toArray` giữ nội dung và không cho mảng trả về ghi ngược vào list.
- Iterator không tiêu thụ dữ liệu khi hỏi `hasNext` nhiều lần.
- `next` hoạt động không cần hỏi `hasNext` trước và báo hết đúng loại ngoại lệ.

Không có phép kiểm tra tên lớp, tên trường hay dung lượng mảng nội bộ.

`toArray` không ghi ngược là hợp đồng dữ liệu công khai, dù một triển khai dùng mảng làm kho. Ngược lại, bắt mảng nội bộ phải có chiều dài gấp đôi số phần tử sẽ khóa vào chính sách cấp phát riêng.

### Phần thay thế kiểm tra cả kết quả và tác động

Với hồ sơ cho `set`, bộ kiểm thử xác nhận giá trị cũ trả về và nội dung mới. Sau đó nó tạo một list iterator mới rồi kiểm tra khả năng thay qua iterator theo cờ riêng.

Tạo iterator sau thao tác sửa trực tiếp giúp ca không dựa vào giả định chung về việc một iterator đang tồn tại sẽ quan sát mọi thay thế từ bên ngoài. Nếu muốn kiểm tra snapshot hoặc khả năng quan sát thay đổi, đó nên là một nhóm có chính sách được khai báo riêng.

Đối với hồ sơ không cho thay thế, thao tác dùng chỉ số hợp lệ và giá trị mới thật. Sau ngoại lệ, bộ kiểm thử còn xác nhận nội dung cần giữ nguyên.

### Phần thay đổi kích thước kiểm tra nhiều đường ghi

Với list hỗ trợ, chương trình thêm theo chỉ số, nối cuối, xóa theo chỉ số, xóa giá trị đầu tiên bằng nhau, xóa giá trị không có, xóa khoảng qua view và `clear`.

Khả năng xóa qua iterator được kiểm tra riêng. Hai lần xuất hiện `A` trong `[A,B,A]` giúp phân biệt việc xóa phần tử cuối vừa trả với việc tìm từ đầu rồi xóa nhầm phần tử bằng nhau đầu tiên.

Với list cố định hoặc chỉ đọc, ca kiểm tra những thao tác có tác động thật sự nhận `UnsupportedOperationException`, đồng thời dữ liệu không bị sửa ngoài ý muốn.

`Arrays.asList` là một list kích thước cố định liên kết với mảng được cung cấp. Trong factory ví dụ, mảng được tạo mới từ nguồn cho mỗi lần gọi, nên các ca không chia sẻ một mảng mutable ngoài ý muốn. Xem [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### CopyOnWriteArrayList cho thấy giá trị của hồ sơ riêng

Cấu hình này vượt qua các ca sửa list trực tiếp và chuỗi mô hình, nhưng các ca iterator lại xác nhận rằng ghi qua iterator không được hỗ trợ.

Nếu bộ kiểm thử dùng một cờ `resizable` rồi tự suy ra iterator phải xóa được, nó sẽ báo lỗi cho một đối tượng đang làm đúng hợp đồng của chính nó.

Đây cũng là lý do không nên chia bài kiểm thử chỉ theo tên lớp rồi viết một bản hoàn toàn khác cho từng tên. Phần hành vi chung vẫn dùng lại, còn khác biệt được biểu diễn bằng khả năng thật sự.

### Lớp cố ý sai giúp kiểm tra bộ kiểm thử

`WrongReturnList` thay dữ liệu đúng nhưng trả giá trị mới thay vì giá trị cũ. Nếu bộ kiểm thử chỉ quan sát nội dung, lỗi này có thể bị bỏ qua.

Dòng `deliberately broken = DETECTED: set must return previous value` xác nhận ca về giá trị trả về đã phát hiện lỗi được cài vào.

Đây là một thí nghiệm đơn giản về việc tạo biến thể sai để xem bài kiểm thử có phát hiện không. Nó không chứng minh bộ kiểm thử phát hiện mọi lỗi. Có thể tiếp tục thiết kế các biến thể có lý do khác: bỏ qua chèn cuối, xóa sai lần xuất hiện, iterator trả thiếu phần tử, view sửa bản sao thay vì gốc.

Không cần giữ các lớp sai trong mã sản phẩm. Ý nghĩa của thí nghiệm là xem mỗi lời hứa quan trọng có một phép kiểm tra thực sự phân biệt được đúng và sai hay chưa.

## Kiểm thử bằng mô hình sau mỗi bước

Một lỗi cấu trúc có thể chỉ xuất hiện sau một chuỗi thao tác: thêm, thay, xóa, xóa hết rồi thêm lại. Một ca ngắn độc lập cho từng phương thức chưa chắc tạo ra chuỗi đó.

Trong `modelSequence`, chương trình giữ:

- `model`: một `ArrayList` làm mô hình tham chiếu cho dữ liệu có thứ tự.
- `actual`: đối tượng cần kiểm tra.
- Một nguồn số giả ngẫu nhiên với seed cố định.
- Một chuỗi thêm, thay, xóa theo chỉ số, xóa theo giá trị và xóa hết.

Sau mỗi bước, chương trình so cả giá trị trả về liên quan, kích thước và dãy phần tử. Nó không chỉ so ở cuối, vì lỗi trung gian có thể bị thao tác sau vô tình che mất.

Chỉ số được sinh dựa trên trạng thái mô hình để tạo thao tác hợp lệ. Những ca chỉ số không hợp lệ đã có nhóm riêng. Tách hai nhóm giúp biết lỗi đến từ xử lý trạng thái hay kiểm tra tiền điều kiện.

### Seed cố định làm lỗi tái hiện được

Seed `2026L` và cùng chuỗi gọi `Random` cho cùng chuỗi số giả ngẫu nhiên. Đây là tính chất được `java.util.Random` công bố, xem [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html).

Trong bài, mỗi hồ sơ phù hợp chạy 200 bước với seed ấy. Nếu mở rộng bộ sinh, nên lưu cả seed và nhật ký thao tác khi lỗi, vì thay đổi cách sinh số hoặc thêm một lần gọi `nextInt` cũng làm chuỗi thao tác phía sau đổi.

Khi gặp lỗi, rút chuỗi về một phản ví dụ ngắn:

~~~text
Chuỗi dài gây lỗi
    -> bỏ bớt các đoạn không cần
    -> giữ lại chuỗi vẫn tái hiện
    -> xác định tiền điều kiện và lời hứa bị phá
    -> thêm ca hồi quy ngắn, có tên rõ
~~~

Ví dụ trên chỉ minh họa quy trình phân tích lỗi; chương trình đầy đủ không cài thuật toán tự rút gọn chuỗi.

### Mô hình tham chiếu cũng có giới hạn

Dùng `ArrayList` làm tham chiếu phù hợp với hồ sơ list có cùng thứ tự, cùng miền giá trị và cùng khả năng trực tiếp đang được thử. Nó không phù hợp để bắt một set giữ phần tử trùng, hay bắt một priority queue phục vụ FIFO.

Chạy candidate cũng là `ArrayList` đối chiếu với mô hình `ArrayList` chủ yếu xác minh cách tổ chức bộ sinh; nó không tạo một bằng chứng độc lập mạnh về mọi hành vi của `ArrayList`. Vì vậy, bài còn có các kỳ vọng tường minh và lớp tùy chỉnh.

Số 200 bước hoặc số checks trong stdout là thông tin về thí nghiệm đã chạy, không là thước đo đầy đủ của hợp đồng. Một phép kiểm tra đúng vào giá trị trả về có thể quan trọng hơn hàng nghìn thao tác không quan sát giá trị đó.

## So sánh đúng theo loại cấu trúc

### List: giữ thứ tự và số lần xuất hiện

Với `List`, `[A,B,A]` khác `[A,A,B]`. Chuyển cả hai sang set làm mất thông tin và có thể khiến bài kiểm thử bỏ qua lỗi thứ tự hoặc xóa thiếu phần tử trùng.

Nếu dữ liệu có đối tượng mutable, hãy giữ kỳ vọng ổn định. Nếu kỳ vọng và kết quả cùng trỏ tới một đối tượng bị sửa, cả hai có thể đổi giống nhau và khiến một ca sai vẫn vượt qua.

Khi điều cần bảo vệ là danh tính của đúng lần xuất hiện, kiểm tra thêm tham chiếu hoặc trường nhận diện riêng phù hợp. Kiểm thử theo hợp đồng không cấm dùng phép so sánh danh tính; nó chỉ yêu cầu danh tính thật sự là điều cần quan sát trong ca đó.

### Set: kiểm tra tính duy nhất, không bịa thứ tự

Với một set theo ngữ nghĩa bằng nhau thông thường:

- Thêm một phần tử mới làm thay đổi set.
- Thêm một đối tượng bằng phần tử đã có không tạo thêm thành viên.
- Các phần tử bằng nhau không xuất hiện hai lần khi duyệt.
- Hai set có cùng phần tử cần tương thích về `equals/hashCode`, bất kể thứ tự duyệt.

Không chỉ chuẩn hóa kết quả bằng `new HashSet<>(actual)` rồi kết luận candidate không có phần tử trùng. Phép chuẩn hóa đó tự loại trùng và có thể che một set cài sai. Cần kiểm tra thêm số phần tử duyệt, kích thước và tính duy nhất của candidate.

Với một collection dạng túi cho phép trùng nhưng không có thứ tự, so sánh bảng tần suất thường phù hợp hơn so sánh set. Với `Set` có thứ tự được công bố, bổ sung nhóm kiểm tra thứ tự riêng. Hợp đồng nền về tính duy nhất của set nằm trong [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### Map: so ánh xạ và các view

Với map không có thứ tự được công bố, nội dung được mô tả bằng các cặp khóa–giá trị, không phải chuỗi `toString`.

Những ca có ích khi thao tác được hỗ trợ:

1. Thêm khóa mới, kiểm tra kích thước và giá trị.
2. `put` vào khóa đã có, kiểm tra giá trị cũ trả về và kích thước không tăng.
3. Xóa khóa có và không có.
4. Với map cho phép giá trị `null`, phân biệt khóa vắng với khóa hiện diện có giá trị `null` bằng `containsKey`.
5. Lấy các view rồi kiểm tra tác động ghi ngược được công bố.
6. Kiểm tra `Entry.setValue` theo khả năng hỗ trợ, không chỉ `map.put`.

`get(key) == null` không đủ chứng minh khóa vắng trong map cho phép giá trị `null`. Tương tự, chặn `put` chưa chứng minh mọi entry và view đều chỉ đọc.

Một model map phải dùng cùng ngữ nghĩa so sánh khóa của đối tượng cần thử. Không dùng mô hình dựa trên `equals` cho một cấu trúc cố ý công bố ngữ nghĩa khóa khác rồi gọi mọi khác biệt là lỗi. Xem các quy tắc ánh xạ và view trong [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Queue: phân biệt thứ tự lấy với thứ tự duyệt

`Queue` không có một quy tắc FIFO áp dụng cho mọi triển khai. Có queue ưu tiên và cách tổ chức khác; mỗi triển khai phải nêu chính sách của mình.

Với một queue FIFO đã công bố, kiểm tra các lần lấy trả đúng thứ tự thêm. Với queue ưu tiên, kiểm tra phần tử lấy đầu phù hợp comparator; nếu comparator coi hai phần tử bằng nhau mà API không hứa ổn định, đừng tự buộc thứ tự chèn giữa chúng.

Cũng cần kiểm tra cặp hành vi:

| Tình huống | Phương thức báo bằng giá trị | Phương thức báo bằng ngoại lệ |
| --- | --- | --- |
| Queue rỗng, lấy đầu | `poll()` trả `null` | `remove()` ném `NoSuchElementException` |
| Queue rỗng, xem đầu | `peek()` trả `null` | `element()` ném `NoSuchElementException` |
| Queue giới hạn đầy | `offer(e)` trả `false` | `add(e)` ném `IllegalStateException` |

Chính sách `null` cần xem riêng theo queue, không tự suy ra mọi queue đều có cùng hạn chế. Các khác biệt này được mô tả trong [Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

## Các điều không nên đưa vào bộ kiểm thử chung

### Không khẳng định kết quả trong vùng hành vi không được xác định

Ví dụ, sửa cấu trúc một list trực tiếp trong khi đang dùng view hoặc iterator có thể rơi vào trường hợp mà hợp đồng không định nghĩa một kết quả chung. Một bài kiểm thử không nên vừa vi phạm điều kiện sử dụng vừa đòi dữ liệu cuối cụ thể cho mọi list.

Với iterator có chính sách fail-fast, có thể kiểm tra các trường hợp tuần tự theo tài liệu triển khai. Nhưng không biến một lần không có CME thành bằng chứng không có tranh chấp, và không dùng việc chắc chắn có CME làm nền tảng đúng đắn của thuật toán đồng thời. Xem [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html).

Tương tự, không viết ca chung yêu cầu `Iterator.remove` sau `forEachRemaining` luôn hoạt động. Hợp đồng tổng quát không bảo đảm hành vi đó. Xem [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

### Không mặc định mọi thao tác hàng loạt là giao dịch

Nếu `addAll` xử lý lần lượt rồi gặp phần tử không hợp lệ, một phần dữ liệu có thể đã được thêm. Nếu callback của một phép cập nhật ném lỗi giữa chừng, cũng không tự có hoàn tác.

Bộ kiểm thử chỉ yêu cầu “toàn bộ thành công hoặc dữ liệu không đổi” khi API thật sự hứa bảo đảm ấy. Nếu không, nên kiểm tra những hậu điều kiện được xác định và tách ca kiểm tra bảo đảm mạnh của lớp riêng.

Khi cố ý tạo ngoại lệ trong callback, giữ lại thông tin về thứ tự thao tác có bảo đảm. Không tự suy ra callback của một cấu trúc không thứ tự sẽ đi qua cùng một khóa trước trong mọi lần chạy.

### Không kiểm tra số lần gọi nội bộ nếu API không hứa

Một cấu trúc băm có thể dùng hash để loại phần tử không thể bằng nhau mà không gọi `equals` cho mọi phần tử. Một thuật toán có thể dùng iterator hoặc chỉ số. Bắt buộc số lần `equals/get/iterator` chính xác dễ làm bài kiểm thử thất bại khi có một tối ưu hợp lệ.

Nếu số lần gọi có ý nghĩa nghiệp vụ, chẳng hạn một API công bố điều kiện gọi hàm tính giá trị, kiểm tra đúng bảo đảm công khai đó. Đừng tự áp một sơ đồ gọi quan sát được trong một phiên bản thành hợp đồng của interface.

## Tách ba loại bằng chứng

### Bằng chứng hành vi

Quan sát qua API công khai: kết quả, dữ liệu, ngoại lệ, view, thứ tự và các quan hệ giữa thao tác. Đây là phần có thể dùng chung rộng nhất.

### Bằng chứng bất biến nội bộ

Khi tự phát triển cấu trúc dữ liệu, có thể cần kiểm tra các nút liên kết khớp hai chiều, phần mảng ngoài `size` không giữ tham chiếu thừa, hoặc số entry ở các vùng lưu trữ khớp số đếm.

Đây là các kiểm tra có giá trị cho đúng cài đặt đó. Hãy gọi đúng tên và đặt chúng ở phạm vi phù hợp; không ép lớp có kho dữ liệu khác cung cấp cùng trường hoặc cùng bất biến vật lý.

Một thay đổi từ mảng sang liên kết có thể cần viết lại nhóm nội bộ mà vẫn giữ nguyên nhóm hành vi. Điều đó là dấu hiệu ranh giới kiểm thử được tổ chức đúng.

### Bằng chứng hiệu năng và đồng thời

Nếu có yêu cầu hiệu năng, cần phương pháp đo thích hợp với dữ liệu, trạng thái JVM và điều kiện môi trường. Một assertion thời gian rất nhỏ trong ca chức năng thường không chứng minh được độ phức tạp hoặc khả năng chịu tải.

Nếu có yêu cầu đồng thời, phải kiểm tra đúng bảo đảm đồng thời. Một bài tuần tự vượt qua không chứng minh tính nguyên tử. Dùng mốc phối hợp rõ thay cho `sleep` để đoán lịch chạy, và kiểm tra kết quả sau khi các luồng được chờ hoàn tất.

Ví dụ, với `ConcurrentHashMap`, không yêu cầu các phép đọc tổng hợp trong lúc có ghi đồng thời phải là snapshot toàn map. Chính sách quan sát được mô tả riêng trong [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html). Một model tuần tự có thể dùng ở trạng thái đã ổn định, còn kiểm tra trong thời gian cập nhật phải theo hợp đồng đồng thời tương ứng.

## Quy trình xây một bộ kiểm thử cho collection tùy chỉnh

1. Viết các lời hứa công khai bằng ngôn ngữ hành vi: loại cấu trúc, khả năng ghi, `null`, thứ tự, view và đồng thời.
2. Chọn interface cùng hồ sơ phù hợp; ghi tiền điều kiện của dữ liệu sinh.
3. Tạo factory cho các đối tượng độc lập theo nhu cầu kiểm thử.
4. Viết ca tường minh cho kết quả trả về, tác động và ngoại lệ ở biên.
5. Đưa nhiều triển khai hợp lệ vào cùng nhóm để tìm giả định vô tình về lớp.
6. Thêm chuỗi thao tác và so mô hình sau từng bước khi có model phù hợp.
7. Tạo một số biến thể sai có chủ đích để xem nhóm kiểm tra quan trọng có phát hiện không.
8. Tách các kiểm tra nội bộ, hiệu năng và đồng thời khỏi phần hợp đồng chung.
9. Khi có lỗi mới, giữ phản ví dụ ngắn thành ca hồi quy có tên rõ.

Nếu thay một lớp hợp lệ khác mà bài kiểm thử thất bại, đừng vội sửa lớp mới hoặc xóa kỳ vọng. Hãy tìm nguồn của kỳ vọng: nó là hợp đồng thật, khả năng đã chọn sai, hay chi tiết cài đặt bị mang vào ca chung?

## Bài tập tự kiểm tra

### 1. Hàm trả List nhưng test bắt ArrayList

Yêu cầu của hàm chỉ nói trả danh sách giữ thứ tự kết quả và cho đọc theo chỉ số. Test kiểm tra chính xác lớp runtime là `ArrayList`.

**Đáp án:** Kỳ vọng về lớp quá chặt so với yêu cầu đã nêu. Kiểm tra dãy phần tử và hành vi đọc; chỉ kiểm tra lớp nếu API cố ý có lời hứa cụ thể về lớp đó.

### 2. Vì sao đổi list thành set trước khi so có thể che lỗi?

Kết quả mong đợi là `[A,B,A]` nhưng kết quả thật là `[B,A]`.

**Đáp án:** Cả hai có thể trở thành cùng set `{A,B}`. Phép chuyển mất số lần xuất hiện và thứ tự, trong khi đó là phần của hợp đồng list.

### 3. List thêm được nhưng iterator.remove ném UOE có luôn sai không?

Đối tượng là một list có iterator snapshot chỉ đọc được công bố rõ.

**Đáp án:** Không. Khả năng sửa list và sửa qua iterator là hai điều khác. Bộ kiểm thử phải khai báo riêng và chọn đúng kỳ vọng cho từng đường.

### 4. addAll rỗng không lỗi có chứng minh thêm được không?

Collection không thay đổi sau `addAll(List.of())` và phương thức kết thúc bình thường.

**Đáp án:** Không. Không có phần tử nào cần được thêm. Dùng hợp đồng đã công bố, và kiểm tra thao tác có tác động thật nếu muốn xác minh khả năng thêm.

### 5. Lớp set có iterator chứa trùng nhưng new HashSet(actual) đúng

Sau khi chuẩn hóa kết quả sang `HashSet`, tập phần tử đúng như mong đợi.

**Đáp án:** Phép chuẩn hóa có thể đã tự loại trùng và che lỗi. Cần kiểm tra số lần duyệt, kích thước và tính duy nhất của candidate trước khi làm mất thông tin.

### 6. set thay đúng dữ liệu nhưng trả giá trị mới

Các kiểm tra nội dung đều vượt qua.

**Đáp án:** Vẫn vi phạm hợp đồng `List.set`, vốn trả giá trị cũ. Cần assertion riêng cho kết quả trả về; `WrongReturnList` trong chương trình minh họa đúng lỗi này.

### 7. Một seed chạy 200 bước thành công có chứng minh hoàn chỉnh không?

Ba triển khai vượt qua cùng một chuỗi thao tác với seed cố định.

**Đáp án:** Không. Đó là bằng chứng cho chuỗi đã thử. Vẫn cần ca biên, các khả năng chưa được sinh, model đúng ngữ nghĩa và kiểm tra những lời hứa quan trọng bằng các phép quan sát độc lập.

### 8. Kiểm tra nội bộ có phải luôn là việc không nên làm?

Một cấu trúc liên kết tự viết có thể bị sai con trỏ ngược nhưng các ca đơn giản chưa thấy lỗi.

**Đáp án:** Kiểm tra bất biến nội bộ có giá trị cho cài đặt đó. Tách nó khỏi bộ hợp đồng công khai dùng chung để có thể thay kho dữ liệu mà không làm lẫn lời hứa bên ngoài với cách tổ chức bên trong.
