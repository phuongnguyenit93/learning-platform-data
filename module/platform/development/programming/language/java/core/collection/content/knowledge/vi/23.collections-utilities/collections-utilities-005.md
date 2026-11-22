# fill và nCopies: thay phần tử so với tạo danh sách

## 1. Hai nhu cầu giống hình thức nhưng khác thao tác

Một danh sách đã có năm trạng thái và cần đặt tất cả về “chờ xử lý”. Một danh sách khác chưa tồn tại và cần có ngay năm vị trí ban đầu mang cùng giá trị. Kết quả nhìn bên ngoài đều có thể là năm chữ giống nhau, nhưng cách làm khác nhau:

- Collections.fill(list,value) **thay các phần tử ở những vị trí đã tồn tại trong list**.
- Collections.nCopies(n,value) **trả về một List có kích thước n, biểu diễn n lần lặp của cùng value**.

fill là thao tác cập nhật list được truyền vào; nCopies là phương thức tạo kết quả để nơi gọi sử dụng. Không dùng hai tên như những cách viết thay thế tùy ý.

Một khác biệt nữa cần biết ngay: nCopies không tạo n đối tượng phần tử mới. Nếu value là tham chiếu tới đối tượng có thể thay đổi, mọi vị trí lặp cùng tham chiếu đó. fill cũng đặt cùng một tham chiếu vào các vị trí được thay.

| Câu hỏi | fill(list,value) | nCopies(n,value) |
|---|---|---|
| Đầu vào chính | Một list đã có | Số vị trí cần có và phần tử lặp |
| Tác động | Thay phần tử của list đầu vào | Trả một list kết quả |
| Giá trị trả về | void | List<T> |
| Kích thước sau thao tác | Giữ nguyên size của list | Bằng n nếu n hợp lệ |
| Cần list đầu vào cho phép thay phần tử? | Có, khi thực sự phải thay | Không nhận list đầu vào |
| Kết quả có sửa cấu trúc/vị trí được không? | Phụ thuộc list được truyền vào | List kết quả không cho sửa |
| Có tạo một đối tượng value mới cho từng vị trí? | Không | Không |

Bài học dùng Java 17 trở lên, chỉ dùng thư viện chuẩn. Ba chương trình đầy đủ kiểm tra thay phần tử, tạo list lặp và vấn đề tham chiếu dùng chung. Những đoạn giải thích về null, list rỗng và lớp bọc đều được xét theo hợp đồng của list thực tế.

## 2. fill: thay toàn bộ phần tử hiện có

### 2.1. Thao tác theo size, không theo capacity

Collections.fill có thể được hiểu về tác dụng như: với mỗi chỉ số từ 0 đến size - 1, đặt phần tử tại chỉ số đó thành value. Đây là mô tả ý nghĩa, không bắt buộc thư viện dùng đúng một vòng lặp set(index,...) trên mọi loại List.

Sau khi hoàn tất trên một list thông thường hợp lệ:

- size không đổi.
- Thứ tự các vị trí vẫn là các vị trí cũ.
- Phần tử tại mỗi vị trí được thay bằng value.
- Không có phần tử mới được thêm để tăng kích thước.

new ArrayList<>(5) tạo ArrayList rỗng với dung lượng ban đầu phù hợp để chứa thêm dữ liệu về sau. Nó không tạo sẵn năm phần tử null.

Vì size vẫn bằng 0, fill lên list này không tạo ra năm vị trí. Dung lượng (capacity) là khả năng lưu trữ nội bộ; kích thước (size) là số phần tử hiện có theo API.

Tài liệu [ArrayList(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(int)) xác định constructor này tạo list rỗng. [Collections.fill](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#fill(java.util.List,T)) quy định thao tác thay phần tử của list đã có.

### 2.2. Cần hỗ trợ set, không nhất thiết hỗ trợ add/remove

Một list có kích thước cố định vẫn có thể cho phép thay phần tử. Arrays.asList(array) là ví dụ: không thêm/xóa để đổi kích thước được, nhưng có thể set phần tử và cập nhật mảng được bọc.

Bởi vậy fill có thể thành công trên Arrays.asList. Ngược lại, list không cho sửa như List.of hoặc lớp bọc Collections.unmodifiableList chặn việc thay phần tử qua giao diện list, nên fill khi phải thay phần tử sẽ bị từ chối.

Phân biệt hai thuộc tính:

- **Không đổi kích thước được:** chưa đủ kết luận set không được.
- **Không thay phần tử qua list được:** không đáp ứng yêu cầu cập nhật của fill.

fill trả void. Không gán kết quả của lời gọi vào một biến List với ý định nhận “danh sách sau khi điền”; chính list đầu vào là nơi đã thay đổi.

### 2.3. Giá trị null phụ thuộc chính sách của list đích

fill không có quy tắc cấm null chung giống List.of. Nếu list đích cho phép null và hỗ trợ thay phần tử, có thể dùng fill(list,null).

Nếu list đích hoặc lớp bọc có ràng buộc khác, thao tác vẫn phải tuân theo ràng buộc đó. Một kiểu List không bảo đảm mọi triển khai đều nhận mọi giá trị.

Truyền list bằng null là trường hợp khác: không có list để cập nhật và không hợp lệ. Không nhầm “phần tử thay thế có thể là null” với “list đích có thể là null”.

## 3. Chương trình fill: kích thước, mảng và một đoạn list

Tệp **FillExistingListDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class FillExistingListDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Collections.fill(values, "x");
        System.out.println("filled=" + values);
        System.out.println("size=" + values.size());
        Collections.fill(values, null);
        System.out.println("filledNull=" + values);

        List<String> capacityOnly = new ArrayList<>(5);
        Collections.fill(capacityOnly, "ready");
        System.out.println("capacityOnlySize=" + capacityOnly.size());
        System.out.println("capacityOnlyValues=" + capacityOnly);

        String[] array = {"red", "green", "blue"};
        List<String> fixedSize = Arrays.asList(array);
        Collections.fill(fixedSize, "gray");
        System.out.println("fixedSize=" + fixedSize);
        System.out.println("backingArray=" + Arrays.toString(array));

        List<String> parent =
                new ArrayList<>(List.of("a", "b", "c", "d"));
        Collections.fill(parent.subList(1, 3), "m");
        System.out.println("parentAfterRangeFill=" + parent);

        expectUOE("fillReadOnly",
                () -> Collections.fill(List.of("a", "b"), "x"));
        List<String> wrapped = Collections.unmodifiableList(
                new ArrayList<>(List.of("a", "b")));
        expectUOE("fillWrapped",
                () -> Collections.fill(wrapped, "x"));

        int[] numbers = {1, 2, 3};
        Arrays.fill(numbers, 7);
        System.out.println("primitiveArray=" + Arrays.toString(numbers));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 FillExistingListDemo.java
java FillExistingListDemo
```

Stdout chính xác:

```text
filled=[x, x, x]
size=3
filledNull=[null, null, null]
capacityOnlySize=0
capacityOnlyValues=[]
fixedSize=[gray, gray, gray]
backingArray=[gray, gray, gray]
parentAfterRangeFill=[a, m, m, d]
fillReadOnly=UnsupportedOperationException
fillWrapped=UnsupportedOperationException
primitiveArray=[7, 7, 7]
```

### 3.1. Điền giá trị không tăng kích thước

values ban đầu có ba phần tử. Sau fill bằng x, nó vẫn có ba phần tử. Sau fill bằng null, nó vẫn có ba vị trí nhưng mỗi vị trí giữ null.

capacityOnly được khởi tạo bằng new ArrayList<>(5), nên vẫn rỗng trước và sau fill. Không có lỗi ở ví dụ list rỗng cho phép sửa này, nhưng cũng không có “năm giá trị ready” được tạo ra.

Nếu muốn tạo sẵn năm vị trí, phải thêm năm phần tử bằng cách thích hợp hoặc tạo dữ liệu khởi tạo có kích thước năm. nCopies là một lựa chọn khi các vị trí ban đầu dùng cùng giá trị.

### 3.2. Fill trên list dựa vào mảng cập nhật mảng nguồn

fixedSize là view list của array. fill thay ba phần tử của fixedSize thành gray, nên array cũng hiện gray ở cả ba ô.

Nó không tạo ra một mảng mới và không làm list trở thành cấu trúc độc lập. Nếu cần một list riêng, phải sao chép sang cấu trúc riêng trước.

[Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) mô tả quan hệ dựa trên mảng này. Tính kích thước cố định không ngăn phép thay giá trị trong các vị trí đã có.

### 3.3. Fill một phạm vi bằng subList

parent.subList(1,3) là view của các vị trí chỉ số 1 và 2, không gồm chỉ số 3. fill trên view đó làm parent từ [a,b,c,d] thành [a,m,m,d].

Đây là dùng một view để giới hạn những vị trí được thay, không phải fill tự có tham số from/to. Các điều kiện về tính hợp lệ của subList vẫn phải được giữ: không sửa cấu trúc list cha ngoài quy tắc của view trong lúc sử dụng nó.

### 3.4. Với mảng nguyên thủy, dùng API của mảng

Chương trình dùng Arrays.fill(numbers,7) cho int[]. Collections.fill nhận List, không nhận trực tiếp int[].

Cũng không coi Arrays.asList(intArray) là một List<Integer> chứa từng số. Mảng nguyên thủy có thể trở thành một phần tử kiểu int[] trong list do cách truyền kiểu; nó không tự được chuyển thành các Integer riêng để fill như danh sách số.

Arrays.fill là công cụ phù hợp để gán giá trị vào các ô của mảng nguyên thủy. Thao tác ấy vẫn không tăng độ dài mảng.

## 4. nCopies: tạo một list lặp, không sửa list có sẵn

### 4.1. Kích thước là n, giá trị tại mọi vị trí là phần tử đã truyền

Collections.nCopies(n,value) trả List<T> biểu diễn n lần xuất hiện của value.

- n > 0: list có n vị trí.
- n == 0: list rỗng.
- n < 0: IllegalArgumentException.
- value có thể là null.
- Kết quả không cho thay phần tử hoặc sửa cấu trúc theo giao diện list.

Đây là list có phần tử lặp hợp lệ, không phải Set và không loại trùng. Từ copies trong tên không phải lời hứa gọi clone hoặc constructor của value nhiều lần.

Nếu cần thay các vị trí về sau, hãy tạo một list cho phép sửa từ dữ liệu lặp đó, chẳng hạn new ArrayList<>(Collections.nCopies(n,value)).

### 4.2. Biểu diễn lặp gọn hơn việc dựng n phần tử riêng

Tài liệu [Collections.nCopies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)) mô tả một biểu diễn nhỏ giữ một tham chiếu tới đối tượng được lặp.

Điều này cho phép biểu diễn nhiều vị trí có cùng phần tử mà không phải tạo n đối tượng phần tử. Cần phân biệt kích thước logic của List với số đối tượng dữ liệu thật sự được tạo cho các phần tử.

Đọc get(i) ở các chỉ số hợp lệ đều nhận cùng giá trị/tham chiếu value. Duyệt hết list hoặc sao chép nó sang một ArrayList vẫn phải xử lý n vị trí logic.

### 4.3. Không cho sửa list không đồng nghĩa phần tử bất biến

Nếu value là String, việc dùng chung tham chiếu thường không gây lo ngại về sửa nội dung String vì String bất biến.

Nếu value là Box có thể thay đổi, nơi gọi vẫn có thể lấy Box qua get rồi sửa thuộc tính của Box. Điều đó không phải gọi set trên List và không tự bị List chặn.

Phần này sẽ được kiểm chứng bằng so sánh tham chiếu và số lần gọi constructor trong chương trình thứ ba.

## 5. Chương trình nCopies: list chỉ đọc và bản cho phép sửa có sẵn vị trí

Tệp **NCopiesListDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class NCopiesListDemo {
    private static void expect(String label,
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (RuntimeException failure) {
            if (!type.isInstance(failure)) {
                throw failure;
            }
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> repeated = Collections.nCopies(4, "x");
        System.out.println("repeated=" + repeated);
        System.out.println("size=" + repeated.size());
        System.out.println("zero=" + Collections.nCopies(0, "x"));
        System.out.println("nullable=" + Collections.nCopies(2, null));
        expect("negativeCount", IllegalArgumentException.class,
                () -> Collections.nCopies(-1, "x"));
        expect("setRepeated", UnsupportedOperationException.class,
                () -> repeated.set(0, "y"));
        expect("addRepeated", UnsupportedOperationException.class,
                () -> repeated.add("y"));
        expect("fillRepeated", UnsupportedOperationException.class,
                () -> Collections.fill(repeated, "y"));

        List<String> editable = new ArrayList<>(repeated);
        editable.set(0, "first");
        editable.add("tail");
        System.out.println("originalRepeated=" + repeated);
        System.out.println("editable=" + editable);

        List<String> slots =
                new ArrayList<>(Collections.nCopies(3, null));
        slots.set(1, "ready");
        System.out.println("initializedSlots=" + slots);

        List<String> appended = new ArrayList<>(List.of("prefix"));
        appended.addAll(Collections.nCopies(2, "v"));
        System.out.println("appended=" + appended);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NCopiesListDemo.java
java NCopiesListDemo
```

Stdout chính xác:

```text
repeated=[x, x, x, x]
size=4
zero=[]
nullable=[null, null]
negativeCount=IllegalArgumentException
setRepeated=UnsupportedOperationException
addRepeated=UnsupportedOperationException
fillRepeated=UnsupportedOperationException
originalRepeated=[x, x, x, x]
editable=[first, x, x, x, tail]
initializedSlots=[null, ready, null]
appended=[prefix, v, v]
```

### 5.1. nCopies có kích thước thật theo API List

repeated có size bằng 4 và đọc ra bốn lần x. Các phép set, add hoặc fill nhằm thay phần tử trong chính list này bị từ chối.

Không dùng nCopies làm “ArrayList đã chuẩn bị” rồi gọi set trực tiếp. Nó đã có vị trí logic nhưng kết quả không cung cấp quyền cập nhật ấy.

Với n == 0, không có phần tử. Không dùng hành vi của các thao tác không có hiệu lực trên một list rỗng để kết luận mọi list cho sửa: ngoại lệ của một số thao tác không có tác dụng còn phụ thuộc hợp đồng cụ thể.

### 5.2. new ArrayList<>(nCopies(...)) tách cấu trúc, không tự clone phần tử

editable là ArrayList mới có bốn phần tử x lấy từ repeated. Nó hỗ trợ set và add, nên trở thành [first,x,x,x,tail]. repeated vẫn giữ bốn vị trí x như trước.

Bản cho phép sửa có cấu trúc riêng, nhưng các đối tượng phần tử ban đầu vẫn là những tham chiếu được sao chép. Với String bất biến ở ví dụ này, sự dùng chung không làm nội dung x đổi. Với đối tượng có thể thay đổi, phải xét tiếp ở chương trình sau.

### 5.3. Chuẩn bị các ô trống có thể gán về sau

slots được tạo bằng new ArrayList<>(Collections.nCopies(3,null)), nên ngay từ đầu đã có size bằng 3. Vì vậy slots.set(1,"ready") hợp lệ và chỉ thay vị trí giữa.

Cách này khác new ArrayList<>(3), vốn chỉ chuẩn bị dung lượng và chưa có vị trí 1 để set.

null ở đây là giá trị được chọn để biểu diễn ô chưa có dữ liệu. Nếu ứng dụng không dùng null cho trạng thái đó, có thể chọn một giá trị mặc định khác hoặc một mô hình trạng thái rõ ràng hơn.

### 5.4. Dùng nCopies làm nguồn cho addAll

appended ban đầu có prefix. addAll(nCopies(2,"v")) thêm hai phần tử v, làm size tăng từ 1 lên 3.

Chính addAll tăng kích thước list đích; nCopies chỉ cung cấp collection nguồn có hai lần lặp. Không nhầm trường hợp này với fill, vốn thay các phần tử hiện có và không thêm vị trí.

## 6. Tham chiếu dùng chung: cả fill và nCopies đều không clone phần tử

### 6.1. Một biểu thức new không tự được đánh giá lại cho từng vị trí

Trong Collections.nCopies(3,new Box(1)), đối số new Box(1) được đánh giá để tạo **một** Box trước khi gọi nCopies. nCopies nhận tham chiếu tới Box ấy rồi biểu diễn nó ở ba vị trí.

Tương tự, Collections.fill(list,new Box(5)) nhận một Box mới được tạo trước lời gọi và đặt cùng tham chiếu đó vào mọi vị trí được thay. Nó không gọi constructor Box riêng cho mỗi phần tử.

Để quan sát, chương trình sau có bộ đếm số lần gọi constructor. Nó còn phân biệt sửa trạng thái của Box, thay tham chiếu trong list và tạo các Box độc lập.

Tệp **SharedRepeatedElementDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SharedRepeatedElementDemo {
    static final class Box {
        static int constructions;
        int value;

        Box(int value) {
            constructions++;
            this.value = value;
        }
    }

    private static List<Integer> values(List<Box> boxes) {
        return boxes.stream().map(box -> box.value).toList();
    }

    public static void main(String[] args) {
        Box.constructions = 0;
        List<Box> repeated = Collections.nCopies(3, new Box(1));
        System.out.println("nCopiesConstructions=" + Box.constructions);
        System.out.println("sameElement=" + (repeated.get(0) == repeated.get(1)));
        repeated.get(0).value = 9;
        System.out.println("repeatedAfterMutation=" + values(repeated));

        List<Box> editableCopy = new ArrayList<>(repeated);
        editableCopy.get(1).value = 10;
        System.out.println("originalAfterCopyMutation=" + values(repeated));
        editableCopy.set(0, new Box(7));
        System.out.println("copyAfterReplacement=" + values(editableCopy));
        System.out.println("originalAfterReplacement=" + values(repeated));

        List<Box> filled = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            filled.add(new Box(-1));
        }
        Box oldFirst = filled.get(0);
        Box.constructions = 0;
        Collections.fill(filled, new Box(5));
        System.out.println("fillConstructions=" + Box.constructions);
        System.out.println("fillSharesElement=" + (filled.get(0) == filled.get(1)));
        filled.get(2).value = 8;
        System.out.println("filledAfterMutation=" + values(filled));
        System.out.println("oldObjectStill=" + oldFirst.value);

        List<Box> independent = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            independent.add(new Box(0));
        }
        independent.get(0).value = 7;
        System.out.println("independent=" + values(independent));
        System.out.println("differentElements=" +
                (independent.get(0) != independent.get(1)));

        List<List<Integer>> sharedRows = new ArrayList<>(
                Collections.nCopies(2,
                        new ArrayList<>(Collections.nCopies(3, 0))));
        sharedRows.get(0).set(1, 9);
        System.out.println("sharedRows=" + sharedRows);
        System.out.println("sameRow=" + (sharedRows.get(0) == sharedRows.get(1)));

        List<List<Integer>> separateRows = new ArrayList<>();
        for (int row = 0; row < 2; row++) {
            separateRows.add(new ArrayList<>(Collections.nCopies(3, 0)));
        }
        separateRows.get(0).set(1, 9);
        System.out.println("separateRows=" + separateRows);
        System.out.println("differentRows=" +
                (separateRows.get(0) != separateRows.get(1)));

        Box.constructions = 0;
        List<Box> empty = Collections.nCopies(0, new Box(99));
        System.out.println("zeroCountSize=" + empty.size());
        System.out.println("zeroCountArgumentConstructions=" + Box.constructions);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SharedRepeatedElementDemo.java
java SharedRepeatedElementDemo
```

Stdout chính xác:

```text
nCopiesConstructions=1
sameElement=true
repeatedAfterMutation=[9, 9, 9]
originalAfterCopyMutation=[10, 10, 10]
copyAfterReplacement=[7, 10, 10]
originalAfterReplacement=[10, 10, 10]
fillConstructions=1
fillSharesElement=true
filledAfterMutation=[8, 8, 8]
oldObjectStill=-1
independent=[7, 0, 0]
differentElements=true
sharedRows=[[0, 9, 0], [0, 9, 0]]
sameRow=true
separateRows=[[0, 9, 0], [0, 0, 0]]
differentRows=true
zeroCountSize=0
zeroCountArgumentConstructions=1
```

### 6.2. Ba vị trí, một Box

nCopiesConstructions bằng 1 và sameElement bằng true. Sửa repeated.get(0).value thành 9 khiến cả ba vị trí đọc ra 9 vì cả ba cùng trả chính Box đó.

Không có ba đối tượng tự đồng bộ giá trị với nhau. Chỉ có một đối tượng được ba vị trí logic tham chiếu tới.

List repeated vẫn không cho set/add theo giao diện của nó. Việc giá trị in ra đổi không chứng minh danh sách đã cho sửa cấu trúc; thao tác đã sửa đối tượng Box được chứa bên trong.

### 6.3. Sao chép sang ArrayList không tự tách Box

editableCopy có cấu trúc ArrayList riêng nhưng lúc tạo vẫn chứa ba tham chiếu tới Box của repeated.

editableCopy.get(1).value = 10 sửa Box dùng chung, làm repeated cũng đọc ra [10,10,10]. Sau đó editableCopy.set(0,new Box(7)) chỉ thay tham chiếu ở vị trí 0 của bản ArrayList.

Bản sao lúc này hiện [7,10,10], còn repeated vẫn hiện [10,10,10]. Đây là khác biệt giữa:

- Sửa đối tượng mà một tham chiếu đang trỏ tới.
- Thay tham chiếu được lưu ở một vị trí của list.

Cấu trúc riêng không đồng nghĩa mọi phần tử cũng riêng.

### 6.4. Fill thay tham chiếu, không sửa đối tượng cũ

filled ban đầu chứa ba Box riêng có value bằng -1. oldFirst vẫn giữ Box đầu tiên ấy.

Sau fill(filled,new Box(5)), list giữ cùng một Box mới ở cả ba vị trí. Sửa value qua vị trí thứ ba thành 8 làm cả list đọc ra [8,8,8]. Nhưng oldFirst.value vẫn là -1.

Vậy fill không gọi một phép “reset” lên từng Box cũ. Nó thay phần tử của list bằng tham chiếu mới, còn đối tượng cũ vẫn giữ trạng thái nếu có nơi khác tiếp tục tham chiếu đến.

Nếu nhiệm vụ thật sự là cập nhật trạng thái của từng đối tượng đang có, cần dùng phương thức cập nhật của các đối tượng đó theo chính sách riêng. fill không thay thế ý nghĩa ấy.

### 6.5. n bằng 0 vẫn đánh giá biểu thức đối số

Collections.nCopies(0,new Box(99)) trả list rỗng, nhưng new Box(99) vẫn được đánh giá một lần trước lời gọi. Bộ đếm vì vậy là 1 dù zeroCountSize bằng 0.

Đây là quy tắc đánh giá đối số của lời gọi Java, không phải nCopies chủ động tạo một phần tử rồi đặt nó vào list rỗng. Không dùng cách truyền một đối tượng có chi phí hoặc tác dụng phụ để suy rằng “n bằng 0 nên biểu thức tạo đối tượng sẽ không chạy”.

Với fill trên list rỗng cũng vậy: một biểu thức đối số như new Box(...) được đánh giá trước khi phương thức thực hiện thao tác, dù không có vị trí để thay.

## 7. Khi cần phần tử hoặc hàng độc lập, tạo ở đúng cấp

### 7.1. Đối tượng mới phải được tạo trong mỗi lần lặp cần tách

Ở phần independent, new Box(0) nằm bên trong vòng lặp, nên có một Box riêng cho mỗi vị trí. Sửa Box đầu thành 7 cho kết quả [7,0,0].

Đây là khác biệt cốt lõi so với nCopies(3,new Box(0)): một bên gọi constructor ở mỗi lần lặp, một bên đánh giá biểu thức đối số một lần.

Nếu việc tạo phần tử được đóng gói trong một hàm hoặc Supplier, nó vẫn phải thực sự trả đối tượng riêng theo hợp đồng của ứng dụng. Chỉ gọi một hàm nhiều lần không bảo đảm độc lập nếu hàm ấy luôn trả một đối tượng dùng chung.

### 7.2. Bẫy ma trận có nhiều hàng cùng tham chiếu

sharedRows được tạo từ nCopies(2,một ArrayList hàng). Bọc kết quả bằng new ArrayList chỉ tạo cấu trúc ngoài riêng; hai vị trí hàng vẫn trỏ tới một ArrayList trong.

Vì vậy sharedRows.get(0).set(1,9) làm cả hai hàng nhìn thấy 9 ở cột 1. sameRow bằng true là bằng chứng trực tiếp về cùng tham chiếu hàng.

separateRows đặt new ArrayList<>(nCopies(3,0)) bên trong vòng lặp từng hàng, nên mỗi hàng có cấu trúc riêng. Cập nhật hàng đầu không đổi hàng thứ hai.

Ở ví dụ đúng, giá trị ô là Integer bất biến. Nếu các ô là đối tượng có thể thay đổi, tạo hàng riêng mới chỉ giải quyết cấp hàng; còn phải quyết định mỗi ô có cần đối tượng riêng không.

Không có một lớp new ArrayList ở ngoài cùng làm mọi tầng dữ liệu tự độc lập.

### 7.3. Dùng chung không luôn là lỗi

Lặp một giá trị bất biến, một ký hiệu trạng thái chung hoặc một đối tượng được thiết kế dùng chung có thể đúng nhu cầu.

Lỗi xuất hiện khi nơi gọi mong mỗi vị trí có trạng thái riêng có thể cập nhật nhưng lại tạo nhiều tham chiếu tới cùng một đối tượng. Vì vậy, trước khi chọn nCopies hoặc fill, cần hỏi “mỗi vị trí cần cùng giá trị hay cần cùng một đối tượng?” và “có vị trí nào sẽ sửa trạng thái riêng về sau không?”.

## 8. Chọn thao tác theo mục đích

| Mục đích | Cách thể hiện |
|---|---|
| Thay mọi phần tử của list hiện có bằng cùng giá trị | Collections.fill(list,value) |
| Tạo list chỉ đọc có n lần cùng phần tử | Collections.nCopies(n,value) |
| Tạo list cho phép sửa có sẵn n vị trí ban đầu | new ArrayList<>(Collections.nCopies(n,value)) |
| Thêm n lần một giá trị vào cuối list hiện có | list.addAll(Collections.nCopies(n,value)) |
| Tạo n đối tượng có thể thay đổi độc lập | Tạo từng đối tượng trong vòng lặp hoặc bằng cơ chế sinh phần tử đúng hợp đồng |
| Thay mỗi phần tử theo một hàm phụ thuộc phần tử cũ | List.replaceAll(operator), nếu list hỗ trợ |
| Bỏ toàn bộ phần tử để size về 0 | clear(), nếu list hỗ trợ |
| Gán giá trị vào các ô của mảng | Arrays.fill(...) |

### 8.1. fill không phải clear rồi add

clear làm list rỗng, size bằng 0. fill giữ size và thay phần tử ở các vị trí cũ.

Nếu clear rồi gọi fill trên ArrayList vừa rỗng, không có vị trí nào để điền lại. Muốn tăng size trở lại phải thêm phần tử bằng thao tác phù hợp.

### 8.2. fill khác replaceAll về cách tính giá trị

fill nhận một đối tượng đã được đánh giá, rồi dùng cùng đối tượng ấy cho các vị trí được thay.

replaceAll nhận một hàm được áp dụng cho từng phần tử theo hợp đồng của List. Nó phù hợp khi giá trị mới phụ thuộc vào phần tử cũ hoặc khi cần gọi một phép tạo mới theo từng phần tử hiện có.

Tuy vậy, replaceAll cũng không tạo vị trí cho một list rỗng. Nó cũng không tự bảo đảm các kết quả của hàm là những đối tượng khác nhau: hàm có thể trả cùng tham chiếu nhiều lần.

Đặc tả [List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)) tách rõ phép biến đổi từng phần tử này với việc gán cùng một phần tử của fill.

### 8.3. nCopies không trải hoặc sao chép nội dung collection được truyền làm phần tử

Nếu value chính là một List, nCopies(n,value) tạo list ngoài lặp tham chiếu tới list trong đó. Nó không tự lấy các phần tử của value rồi tạo n bản sâu.

Tương tự, List.of(Collections.nCopies(3,"x")) là một list có một phần tử là list bên trong, không phải cách tạo trực tiếp ba String x ở tầng ngoài.

Khi đọc code có nhiều tầng generic, hãy xác định kiểu phần tử của mỗi tầng trước khi suy luận kích thước và mức độ độc lập.

## 9. Chi phí, quyền sửa và các giới hạn thực tế

### 9.1. Fill đi qua các vị trí cần thay

Tài liệu fill mô tả thời gian tuyến tính theo số phần tử. Với các list thông thường có thao tác cập nhật phù hợp, nó phải xử lý các vị trí hiện có, không chỉ đổi một biến mô tả cho toàn bộ dữ liệu.

Không suy mọi List có cùng chi phí thực tế cho set. Những kiểu có cơ chế cập nhật đặc biệt, chẳng hạn tạo bản sao nội bộ khi ghi, có thể làm chi phí khác đáng kể. Hiểu dữ liệu đích trước khi dùng fill trong một đường xử lý thường xuyên.

### 9.2. Biểu diễn nCopies gọn không làm mọi thao tác phía sau rẻ

nCopies biểu diễn một phần tử lặp và số lần lặp một cách gọn. Nhưng:

- Duyệt hết hoặc in ra n vị trí vẫn phải xử lý n vị trí.
- new ArrayList<>(nCopies(n,value)) vật chất hóa một cấu trúc ArrayList chứa n tham chiếu.
- addAll vào list đích làm list đích chứa thêm các phần tử tương ứng.
- Đối tượng value có chi phí tạo riêng, diễn ra theo cách ứng dụng đánh giá đối số.

Không dùng tính gọn của list lặp để kết luận một bản ArrayList được sao chép từ nó cũng chỉ cần bộ nhớ không đổi theo n.

### 9.3. Quyền sửa của nguồn/view vẫn có ý nghĩa

fill trên view có thể thay dữ liệu nguồn, như Arrays.asList và subList trong chương trình đầu. Nếu một phương thức chỉ được quyền đọc, không nên nhận một view có thể ghi rồi xem fill là thao tác “chỉnh bản tạm”.

Ngược lại, bọc một nguồn bằng unmodifiableList không làm chủ sở hữu nguồn mất quyền sửa. fill qua lớp bọc bị chặn; fill trực tiếp qua tham chiếu nguồn cho phép sửa có thể vẫn cập nhật dữ liệu mà bên đọc quan sát.

### 9.4. Không tự đóng tài nguyên, hủy đối tượng hoặc khôi phục khi lỗi

Thay một tham chiếu khỏi list không gọi close trên tài nguyên cũ, không xóa mọi trạng thái của đối tượng cũ và không bảo đảm nó lập tức được thu gom. oldFirst trong chương trình vẫn giữ và đọc được Box cũ.

fill cũng không phải một giao dịch với cam kết hoàn tác mọi vị trí nếu một thao tác cập nhật của list đích bị lỗi. Với một list có ràng buộc hoặc triển khai riêng, cần hiểu chính sách cập nhật của nó và không tự coi nguồn như chưa bị động tới sau lỗi.

Khi nhiều luồng cùng đọc/ghi, một chuỗi thay nhiều vị trí không tự trở thành một lần công bố nguyên tử của toàn bộ danh sách. Cần cơ chế phối hợp hoặc mô hình dữ liệu phù hợp nếu bên đọc phải thấy một phiên bản nhất quán.

## 10. Những lỗi thường gặp

| Cách hiểu sai | Kết quả dễ gặp | Cách hiểu đúng |
|---|---|---|
| ArrayList<>(n) đã có n phần tử | Fill không tạo dữ liệu, set ở vị trí tưởng có bị lỗi | Constructor này tạo list rỗng có dung lượng ban đầu |
| Fill tăng size đến số mong muốn | List vẫn giữ size cũ | Fill thay vị trí hiện có |
| List kích thước cố định không thể fill | Bỏ qua trường hợp Arrays.asList hỗ trợ set | Thay phần tử khác với thêm/xóa |
| nCopies trả một ArrayList cho phép sửa | set/add/fill bị UnsupportedOperationException | Tạo ArrayList riêng nếu cần sửa cấu trúc |
| Copies nghĩa là n bản clone của phần tử | Sửa một đối tượng làm mọi vị trí hiện cùng giá trị | Các vị trí lặp cùng tham chiếu |
| New ArrayList ở ngoài làm mọi phần tử độc lập | Bản sao vẫn sửa đối tượng của nguồn | Sao chép cấu trúc là sao chép các tham chiếu |
| Fill “reset” từng đối tượng cũ | Người giữ đối tượng cũ không thấy trạng thái bị reset | Fill thay tham chiếu trong list |
| Tạo ma trận bằng nCopies một hàng | Cập nhật một hàng làm hàng khác đổi theo | Tạo từng hàng riêng nếu cần độc lập |
| n bằng 0 nên biểu thức tạo đối số không chạy | Constructor/tác dụng phụ vẫn xảy ra | Đối số được đánh giá trước lời gọi |
| Fill null làm các đối tượng cũ biến mất ngay | Nơi khác vẫn giữ chúng | Chỉ thay các tham chiếu ở những vị trí của list |

Với null và số lần lặp, cần nhớ riêng: nCopies nhận phần tử null nhưng từ chối n âm. fill phụ thuộc khả năng thay phần tử và chính sách giá trị của list đích.

Không lấy một thao tác không có hiệu lực trên list rỗng làm phép thử tổng quát xem list có cho sửa hay không. Các ví dụ gây UnsupportedOperationException trong bài đều dùng list không rỗng và thao tác thật sự nhằm thay/thêm phần tử.

## 11. Bài tập và lời giải

### Bài 1 — Dung lượng chưa phải phần tử

Tạo List<String> a = new ArrayList<>(4), rồi gọi fill(a,"x"). a có bao nhiêu phần tử?

**Lời giải:** 0. Dung lượng ban đầu 4 không tạo phần tử. Fill không tăng size nên không có vị trí nào được thêm.

### Bài 2 — Tạo các vị trí để set

Muốn một ArrayList có sẵn bốn vị trí null rồi gán chỉ số 2 thành ready, cách new ArrayList<>(4) đã đủ chưa?

**Lời giải:** chưa. Có thể tạo new ArrayList<>(Collections.nCopies(4,null)), rồi set(2,"ready"). Kết quả có size 4. List từ nCopies trực tiếp có size đúng nhưng không cho set, nên cần ArrayList riêng nếu muốn cập nhật.

### Bài 3 — List kích thước cố định

String[] a = {"a","b"}; List<String> v = Arrays.asList(a). Fill v bằng x có bắt buộc lỗi vì không thêm được phần tử không? Mảng a thế nào?

**Lời giải:** không. View này hỗ trợ thay phần tử dù kích thước cố định. Fill thành công và mảng a cũng có x ở hai ô.

### Bài 4 — Tạo n bản hay một bản?

Collections.nCopies(5,new Box(0)) gọi constructor Box bao nhiêu lần do biểu thức new đó? Nếu sửa Box lấy tại vị trí 2, các vị trí khác nhìn thấy gì?

**Lời giải:** biểu thức new tạo một Box. Mọi vị trí đều trả cùng tham chiếu, nên các vị trí khác cũng đọc trạng thái mới của Box sau khi sửa.

### Bài 5 — Fill khác sửa đối tượng cũ

Một list giữ ba Box khác nhau. Có biến outside giữ Box đầu tiên. Sau fill(list,new Box(10)), outside có tự trỏ đến Box mới hoặc bị đổi value thành 10 không?

**Lời giải:** không. Fill thay tham chiếu ở các vị trí list. outside vẫn trỏ Box cũ, với trạng thái cũ nếu không có thao tác khác thay đổi nó.

### Bài 6 — Sao chép list lặp

b = new ArrayList<>(Collections.nCopies(3,sharedBox)). b có cấu trúc sửa được. Điều đó có làm ba Box độc lập không?

**Lời giải:** không. b có ba vị trí riêng của cấu trúc ArrayList, nhưng cả ba chứa cùng tham chiếu sharedBox. Muốn Box độc lập phải tạo đối tượng riêng cho từng vị trí theo nhu cầu.

### Bài 7 — Ma trận hai hàng

Tạo một hàng cho phép sửa r, rồi new ArrayList<>(Collections.nCopies(2,r)). Nếu gọi get(0).set(1,7), hàng thứ hai có thể cũng hiện 7 không?

**Lời giải:** có, vì hai vị trí hàng cùng trỏ tới r. Tạo ArrayList ngoài không sao chép sâu hàng. Để hai hàng độc lập, tạo từng hàng mới bên trong vòng lặp.

### Bài 8 — Biên số lần lặp

nCopies(0,"x"), nCopies(-1,"x") và nCopies(2,null) có kết quả gì?

**Lời giải:** lần lượt là list rỗng, IllegalArgumentException, và list hai phần tử null không cho sửa cấu trúc/vị trí.

### Bài 9 — N bằng 0 và biểu thức đối số

nCopies(0,createExpensiveObject()) có bảo đảm createExpensiveObject không được gọi không?

**Lời giải:** không. Java đánh giá đối số trước lời gọi nên hàm vẫn được gọi một lần. nCopies chỉ nhận kết quả của lời gọi ấy và số lần lặp bằng 0.

### Bài 10 — Chọn thao tác phù hợp

Đã có list ba số [1,2,3]. Cần thay thành [0,0,0] nhưng giữ size; một nhu cầu khác là thêm ba số 0 vào cuối để thành [1,2,3,0,0,0]. Hai trường hợp dùng gì?

**Lời giải:** trường hợp đầu dùng fill trên list có hỗ trợ thay phần tử. Trường hợp sau dùng addAll(Collections.nCopies(3,0)) trên list có hỗ trợ thêm. nCopies cung cấp dữ liệu lặp, còn addAll mới làm list đích lớn lên.

### Bài 11 — Một list ngoài hay ba phần tử?

List.of(Collections.nCopies(3,"x")) có size ở tầng ngoài bằng bao nhiêu?

**Lời giải:** 1. Phần tử duy nhất là list bên trong có ba x. Không có phép tự trải list lồng nhau ở lời gọi này.

### Bài 12 — Giá trị theo phần tử cũ

Đã có list các số và cần mỗi số mới bằng số cũ nhân hai. Fill bằng một giá trị có đáp ứng không?

**Lời giải:** không biểu đạt đúng phép biến đổi từng giá trị. Có thể dùng replaceAll với hàm tương ứng nếu list hỗ trợ thay phần tử, hoặc tạo một kết quả mới theo hợp đồng mong muốn. Fill dùng cùng một đối tượng đối số cho các vị trí, không tự tính theo từng phần tử cũ.

## 12. Tài liệu đối chiếu

- [Collections.fill — thay phần tử của list](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#fill(java.util.List,T)).
- [Collections.nCopies — danh sách lặp một đối tượng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)).
- [ArrayList — kích thước, dung lượng và constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).
- [Arrays.asList và Arrays.fill](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).
- [List — set, replaceAll và subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
