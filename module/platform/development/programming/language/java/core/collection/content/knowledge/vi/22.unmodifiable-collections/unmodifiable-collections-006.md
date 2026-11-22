# Quy tắc null, phần tử trùng và khóa trùng của các factory

## 1. Tạo collection chỉ đọc cũng là chọn chính sách dữ liệu

Một danh sách mã quyền có thể cần giữ hai lần xuất hiện của cùng mã. Một tập mã quyền chỉ cần mỗi mã một lần. Một bảng cấu hình lại cần mỗi khóa có đúng một giá trị. Cả ba kết quả đều có thể không cho sửa, nhưng quy tắc dữ liệu đầu vào không giống nhau.

Các phương thức tạo tĩnh (factory) như List.of, Set.of và Map.of vừa tạo kết quả vừa áp dụng hợp đồng của từng loại:

- List giữ thứ tự và có thể giữ nhiều phần tử bằng nhau.
- Set chỉ giữ một đại diện cho mỗi phần tử theo quan hệ bằng nhau; cách tạo có thể từ chối hoặc gộp đầu vào trùng.
- Map yêu cầu khóa duy nhất; nhiều khóa khác nhau vẫn được phép có cùng giá trị.
- Chính sách không nhận null là một điều kiện riêng, không tự suy ra chỉ từ chữ “chỉ đọc”.

Điểm dễ nhầm nhất: **Set.of từ chối phần tử trùng, còn Set.copyOf chấp nhận collection có phần tử trùng và giữ một đại diện.** Tên cùng có Set và cùng trả kết quả không cho sửa chưa đủ để suy ra cùng quy tắc đầu vào.

Bài này tập trung vào các factory của List, Set, Map, các bản copyOf, Map.entry/Map.ofEntries và các collector tạo kết quả không cho sửa. Phần cuối đối chiếu một số factory cũ để tránh áp quy tắc null của họ of cho mọi API Java.

Ba chương trình đầy đủ dùng Java 17 trở lên và thư viện chuẩn. Những biểu thức gây lỗi được đặt trong hàm kiểm tra nên chương trình vẫn chạy hết. Kết quả của set/map chỉ được in khi thứ tự đã được làm rõ hoặc đã chuyển sang cấu trúc có thứ tự để trình bày.

## 2. Bảng quy tắc cần phân biệt ngay

### 2.1. Các factory chính

| Phương thức | null ở phần tử/khóa/giá trị được đưa trực tiếp vào | Đầu vào trùng | Kết quả khi hợp lệ |
|---|---|---|---|
| List.of(...) | Không nhận phần tử null | Cho phép phần tử trùng | List giữ các vị trí theo thứ tự đối số |
| List.copyOf(collection) | Collection và các phần tử đều không null | Giữ phần tử trùng | List theo thứ tự duyệt đầu vào |
| Set.of(...) | Không nhận phần tử null | Từ chối phần tử trùng bằng IllegalArgumentException | Set không có phần tử trùng |
| Set.copyOf(collection) | Collection và các phần tử đều không null | Gộp phần tử trùng, giữ một đại diện không được cam kết là đầu hay cuối | Set không có phần tử trùng |
| Map.of(k,v,...) | Không nhận khóa hoặc giá trị null | Từ chối khóa trùng bằng IllegalArgumentException; giá trị trùng được phép | Map với các khóa duy nhất |
| Map.ofEntries(entries...) | Không nhận entry, khóa hoặc giá trị null | Từ chối khóa trùng bằng IllegalArgumentException | Map lấy khóa/giá trị từ các entry |
| Map.copyOf(map) | Map, các khóa và các giá trị đều không null | Nhận các ánh xạ hiện tại của map đầu vào; không phát hiện lịch sử ghi đè đã mất trước đó | Map không theo các cập nhật ánh xạ về sau của map nguồn |
| Map.entry(k,v) | Không nhận khóa hoặc giá trị null | Chỉ tạo một entry, chưa có vấn đề trùng giữa nhiều entry | Entry không cho setValue |

Với các trường hợp null bị cấm ở bảng, lời gọi không hợp lệ gây NullPointerException. Đây là lỗi ở bước tạo kết quả, khác UnsupportedOperationException khi cố sửa kết quả đã được tạo thành công.

Map.copyOf nhận một Map chứ không nhận một dãy cặp khóa/giá trị. Một map thông thường đã áp dụng quy tắc khóa duy nhất trước khi copyOf được gọi; cần nhớ khác biệt này khi kiểm tra dữ liệu trùng.

Các kiểu collection cụ thể vẫn có thể có chính sách khác. Ví dụ HashMap mutable cho phép một khóa null và giá trị null; điều đó không làm Map.copyOf nhận được các null ấy.

### 2.2. Quy mô đối số và phiên bản API

List.of và Set.of có các dạng thuận tiện cho số phần tử nhỏ, cùng dạng varargs để nhận nhiều phần tử hơn. Map.of có các dạng từ không ánh xạ đến mười ánh xạ; với nhiều cặp hơn thường dùng Map.ofEntries.

Các phương thức of, Map.ofEntries và Map.entry có từ Java 9. Các bản copyOf có từ Java 10. Mọi API này đều có trên Java 17 dùng trong bài.

List.of(), Set.of(), Map.of() và Map.ofEntries() có thể tạo kết quả rỗng. Rỗng không có nghĩa một factory bắt đầu chấp nhận một phần tử null; “không có phần tử” và “có một phần tử null” là hai dữ liệu khác nhau.

## 3. null: phân biệt đối tượng đầu vào, phần tử và dữ liệu bên trong

### 3.1. null không được tự bỏ qua

List.of("a",null) không tạo list chỉ còn a. Set.of("a",null) không bỏ null để tiếp tục. Map.of("a",null) không bỏ ánh xạ hoặc thay null bằng chuỗi rỗng.

Nếu nghiệp vụ muốn lọc, thay giá trị thiếu hoặc từ chối với thông báo riêng, phải làm việc đó tường minh. Factory không chọn chính sách nghiệp vụ thay ứng dụng.

Cũng cần phân biệt null với dữ liệu khác:

- Chuỗi "null" là một String có bốn ký tự, không phải tham chiếu null.
- Chuỗi rỗng "" vẫn là một String không null.
- Một collection rỗng là một đối tượng collection, không phải null.
- Một đối tượng có một trường bên trong bằng null vẫn có thể là phần tử không null.

### 3.2. copyOf kiểm tra cả nguồn và nội dung cần lấy

List.copyOf(null) không có collection để sao chép nên gây NullPointerException. List.copyOf một ArrayList không null nhưng có phần tử null cũng không hợp lệ.

Set.copyOf có cùng điều kiện không nhận nguồn null và không có phần tử null. Map.copyOf yêu cầu map nguồn không null và không chứa khóa/giá trị null.

Không nhìn kiểu ArrayList hoặc HashMap của nguồn để đoán rằng nội dung chắc chắn phù hợp: chính những lớp nguồn đó cho phép một số null mà factory đích từ chối.

### 3.3. Với varargs, hãy viết ví dụ null không nhập nhằng

Trong Java, một lời gọi chỉ viết List.of(null) có thể liên quan tới việc chọn overload và cách hiểu tham số varargs, đồng thời có thể tạo cảnh báo của compiler. Khi muốn diễn đạt chính xác trường hợp đang thử, nên ghi rõ:

- List.of((String) null): một phần tử String bằng null.
- List.of((String[]) null): mảng varargs bằng null.

Cả hai trường hợp này đều thất bại, nhưng ý nghĩa đầu vào khác nhau. Dùng cast trong ví dụ để giải thích hợp đồng, không phải để lách điều kiện null.

### 3.4. Factory không kiểm tra đệ quy mọi trường của phần tử

List chứa một mảng String[] không null có thể được tạo hợp lệ dù một ô trong mảng là null, miễn mảng đó thật sự là **một phần tử** của list.

Factory chỉ áp điều kiện lên phần tử mà nó nhận ở cấp đó. Nó không tự đi vào mọi mảng, list hoặc đối tượng nghiệp vụ để xác nhận không có null ở bất cứ đâu.

Phần varargs ở cuối chương trình thứ hai sẽ kiểm chứng điều này với List.<String[]>of(...). Nếu API nghiệp vụ cấm cả null trong đối tượng con, phải có kiểm tra mô hình tương ứng.

## 4. Chương trình kiểm tra các factory nhận đối số trực tiếp

DirectFactoryRulesDemo tách từng dữ liệu không hợp lệ thành một lời gọi riêng. Hàm expect chỉ in tên loại ngoại lệ đã xác nhận đúng, không phụ thuộc thông báo hoặc stack trace của một bản JDK cụ thể.

Tệp **DirectFactoryRulesDemo.java**:

```java
import java.util.AbstractMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DirectFactoryRulesDemo {
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
        System.out.println("listDuplicates=" + List.of("x", "x"));
        System.out.println("emptySizes=" +
                List.of().size() + "," + Set.of().size() + "," + Map.of().size());

        expect("listNullElement", NullPointerException.class,
                () -> List.of((String) null));
        expect("listNullArray", NullPointerException.class,
                () -> List.of((String[]) null));
        expect("setNullElement", NullPointerException.class,
                () -> Set.of((String) null));
        expect("setDuplicate", IllegalArgumentException.class,
                () -> Set.of("x", "x"));

        Map<String, Integer> repeatedValues = Map.of("a", 7, "b", 7);
        System.out.println("repeatedMapValueSize=" + repeatedValues.size());
        expect("mapNullKey", NullPointerException.class,
                () -> Map.of((String) null, 1));
        expect("mapNullValue", NullPointerException.class,
                () -> Map.of("a", (Integer) null));
        expect("mapDuplicateKey", IllegalArgumentException.class,
                () -> Map.of("a", 1, "a", 1));

        expect("entryNullValue", NullPointerException.class,
                () -> Map.entry("a", (Integer) null));
        expect("ofEntriesNullEntry", NullPointerException.class,
                () -> Map.ofEntries((Map.Entry<String, Integer>) null));
        expect("ofEntriesNullKey", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>(null, 1)));
        expect("ofEntriesNullValue", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>("a", null)));
        expect("ofEntriesDuplicateKey", IllegalArgumentException.class,
                () -> Map.ofEntries(Map.entry("a", 1), Map.entry("a", 2)));

        Map.Entry<String, Integer> entry =
                new AbstractMap.SimpleEntry<>("a", 1);
        Map<String, Integer> extracted = Map.ofEntries(entry);
        entry.setValue(9);
        System.out.println("extractedValue=" + extracted.get("a"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DirectFactoryRulesDemo.java
java DirectFactoryRulesDemo
```

Stdout chính xác:

```text
listDuplicates=[x, x]
emptySizes=0,0,0
listNullElement=NullPointerException
listNullArray=NullPointerException
setNullElement=NullPointerException
setDuplicate=IllegalArgumentException
repeatedMapValueSize=2
mapNullKey=NullPointerException
mapNullValue=NullPointerException
mapDuplicateKey=IllegalArgumentException
entryNullValue=NullPointerException
ofEntriesNullEntry=NullPointerException
ofEntriesNullKey=NullPointerException
ofEntriesNullValue=NullPointerException
ofEntriesDuplicateKey=IllegalArgumentException
extractedValue=1
```

### 4.1. List giữ trùng; Set xem trùng là lỗi ở họ of

List.of("x","x") tạo hai vị trí cùng giá trị x. Set.of("x","x") bị từ chối. Không dùng Set.of như một phép “loại trùng tiện lợi” cho các đối số không biết trước.

Từ chối trùng phù hợp khi một khai báo lặp lại được xem là lỗi cần phát hiện. Nếu muốn thu các giá trị riêng biệt từ một nguồn có thể lặp, Set.copyOf hoặc một phép thu set với hợp đồng tương ứng sẽ thể hiện mục đích khác.

### 4.2. Map chỉ yêu cầu khóa duy nhất

Map.of("a",7,"b",7) hợp lệ vì có hai khóa khác nhau. Giá trị 7 được dùng cho cả hai ánh xạ không tạo ra xung đột.

Map.of("a",1,"a",1) vẫn bị từ chối dù giá trị cũng giống nhau. Factory không tự chọn “nếu cùng giá trị thì bỏ qua khóa lặp” và cũng không áp quy tắc “cặp sau thắng” như thao tác put lặp trên một map mutable.

Hợp đồng của [Map.of và Map.ofEntries](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)) phân biệt rõ khóa trùng với giá trị trùng.

### 4.3. Map.entry có thể báo lỗi trước Map.ofEntries

Map.entry("a",null) tự thất bại ngay khi tạo entry. Nếu nó nằm trong đối số của Map.ofEntries, chương trình còn chưa có entry hợp lệ để truyền tiếp.

Map.ofEntries cũng phải kiểm tra những entry đến từ nguồn khác. AbstractMap.SimpleEntry trong ví dụ có thể mang null, nên hai phép thử khóa null và giá trị null kiểm tra chính bước trích dữ liệu của ofEntries.

Một tham chiếu entry bằng null cũng bị từ chối. Vì vậy cần kiểm tra ba tầng riêng: mảng/dãy entry, mỗi đối tượng entry, và khóa/giá trị bên trong entry.

### 4.4. Map.ofEntries lấy dữ liệu, không giữ đối tượng entry đầu vào

Ở cuối chương trình, entry mutable ban đầu chứa a→1. Sau khi extracted được tạo, entry.setValue(9) không đổi extracted.get("a"), vẫn là 1.

Điều này minh họa hợp đồng trích khóa/giá trị ra khỏi entry. Nó không sao chép sâu đối tượng khóa hoặc giá trị; nếu giá trị là một đối tượng mutable dùng chung, trạng thái bên trong đối tượng ấy vẫn cần xét riêng.

## 5. “Trùng” dựa vào quan hệ bằng nhau, không dựa vào hình thức hiển thị

### 5.1. Khác tham chiếu vẫn có thể là phần tử hoặc khóa trùng

Hai String được tạo bằng hai đối tượng khác nhau nhưng cùng nội dung vẫn equals nhau. Set.of không coi chúng là hai phần tử riêng chỉ vì == trả false.

Với lớp nghiệp vụ, quy tắc bằng nhau do equals() định nghĩa, cùng hợp đồng hashCode() tương ứng. Nếu hai đối tượng có cùng mã nghiệp vụ được equals xem là bằng nhau, chúng có thể là phần tử trùng hoặc khóa trùng ở các factory này, dù những trường mô tả khác nhau.

Ngược lại, hai đối tượng in ra cùng một chuỗi chưa chắc equals nhau. Không dựa vào toString() để kiểm tra trùng.

### 5.2. Cùng hashCode không có nghĩa là trùng

Hash code hỗ trợ tổ chức tra cứu, không thay cho quan hệ equals. Hai phần tử khác nhau có thể va chạm hash mà vẫn cùng tồn tại.

Ví dụ "FB" và "Ea" có cùng hashCode của String nhưng không bằng nhau theo equals. Set.of("FB","Ea") vì thế có hai phần tử, không bị lỗi trùng.

Nếu lớp tự viết vi phạm hợp đồng equals/hashCode, không dùng một kết quả ngẫu nhiên của factory để suy ra Java đang đổi định nghĩa bằng nhau. Cần sửa hợp đồng lớp trước.

### 5.3. Không tự chuẩn hóa chuỗi hoặc dùng Comparator thay equals

"admin" và "ADMIN" là hai String khác nhau theo equals. Factory không tự chuyển chữ thường, trim khoảng trắng hoặc áp một Comparator không phân biệt hoa/thường.

Nếu nghiệp vụ xem chúng là một mã, phải chuẩn hóa hoặc ánh xạ khóa theo chính sách đã định trước bước tạo collection. Việc đó có thể làm phát sinh xung đột mới mà dữ liệu thô chưa có, nên cần chọn từ chối, gộp hay báo lỗi rõ ràng.

## 6. copyOf: khác biệt quan trọng ở cách xử lý dữ liệu trùng

List.copyOf giữ các phần tử trùng và thứ tự duyệt đầu vào. Set.copyOf nhận một Collection, vì vậy đầu vào hoàn toàn có thể là List có phần tử lặp. Nó tạo set với một đại diện cho mỗi nhóm bằng nhau.

Theo hợp đồng riêng của [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), khi có nhiều đối tượng bằng nhau, đại diện được giữ không được cam kết là đối tượng xuất hiện đầu tiên hoặc cuối cùng.

### 6.1. Chương trình sao chép, equality và mảng

Label trong chương trình chỉ dùng id cho equals/hashCode. Hai Label có cùng id nhưng khác text vì vậy là các đối tượng khác tham chiếu mà vẫn bằng nhau theo quy tắc của lớp.

Tệp **CopyFactoryRulesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CopyFactoryRulesDemo {
    static final class Label {
        final int id;
        final String text;

        Label(int id, String text) {
            this.id = id;
            this.text = text;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Label label && id == label.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

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
        List<String> source = new ArrayList<>(List.of("b", "a", "b"));
        List<String> listCopy = List.copyOf(source);
        Set<String> setCopy = Set.copyOf(source);
        System.out.println("copiedList=" + listCopy);
        System.out.println("copiedSetSorted=" + new TreeSet<>(setCopy));

        expect("copyListNull", NullPointerException.class,
                () -> List.copyOf(Arrays.asList("x", null)));
        expect("copySetNull", NullPointerException.class,
                () -> Set.copyOf(Arrays.asList("x", null)));

        Label first = new Label(1, "first");
        Label second = new Label(1, "second");
        System.out.println("differentObjects=" + (first != second));
        System.out.println("equalElements=" + first.equals(second));
        expect("ofEqualElements", IllegalArgumentException.class,
                () -> Set.of(first, second));
        Set<Label> labels = Set.copyOf(List.of(first, second));
        Label chosen = labels.iterator().next();
        System.out.println("copyDedupSize=" + labels.size());
        System.out.println("representativeIsInput=" +
                (chosen == first || chosen == second));

        System.out.println("sameHash=" + ("FB".hashCode() == "Ea".hashCode()));
        System.out.println("collisionSetSize=" + Set.of("FB", "Ea").size());

        String[] row1 = {"same"};
        String[] row2 = {"same"};
        System.out.println("differentArraySetSize=" + Set.of(row1, row2).size());
        expect("sameArrayRepeated", IllegalArgumentException.class,
                () -> Set.of(row1, row1));
        List<int[]> primitiveArrayElement = List.of(new int[]{1, 2});
        System.out.println("primitiveArrayListSize=" + primitiveArrayElement.size());
        List<String[]> nested = List.<String[]>of(new String[]{"x", null});
        System.out.println("nestedListSize=" + nested.size());
        System.out.println("nestedNullAllowed=" + (nested.get(0)[1] == null));

        Map<String, Integer> staged = new LinkedHashMap<>();
        staged.put("k", 1);
        staged.put("k", 2);
        Map<String, Integer> mapCopy = Map.copyOf(staged);
        System.out.println("stagedSize=" + staged.size());
        System.out.println("copiedMapValue=" + mapCopy.get("k"));

        Map<String, Integer> nullValue = new LinkedHashMap<>();
        nullValue.put("k", null);
        expect("copyMapNullValue", NullPointerException.class,
                () -> Map.copyOf(nullValue));
        Map<String, Integer> nullKey = new LinkedHashMap<>();
        nullKey.put(null, 1);
        expect("copyMapNullKey", NullPointerException.class,
                () -> Map.copyOf(nullKey));
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 CopyFactoryRulesDemo.java
java CopyFactoryRulesDemo
```

Stdout chính xác:

```text
copiedList=[b, a, b]
copiedSetSorted=[a, b]
copyListNull=NullPointerException
copySetNull=NullPointerException
differentObjects=true
equalElements=true
ofEqualElements=IllegalArgumentException
copyDedupSize=1
representativeIsInput=true
sameHash=true
collisionSetSize=2
differentArraySetSize=2
sameArrayRepeated=IllegalArgumentException
primitiveArrayListSize=1
nestedListSize=1
nestedNullAllowed=true
stagedSize=1
copiedMapValue=2
copyMapNullValue=NullPointerException
copyMapNullKey=NullPointerException
```

### 6.2. Đại diện được giữ không phải quy tắc chọn dữ liệu nghiệp vụ

Set.of(first,second) bị lỗi vì hai Label bằng nhau. Set.copyOf(List.of(first,second)) thành công với kích thước 1.

Chương trình chỉ kiểm tra đại diện là một trong hai đối tượng đầu vào. Nó không in nhãn text nào được giữ rồi tuyên bố đó là quy tắc “giữ bản đầu”.

Nếu hai bản có cùng id nhưng khác thông tin mà nghiệp vụ cần xử lý, việc loại trùng tùy ý có thể mất dữ liệu quan trọng. Cần tự kiểm tra xung đột hoặc chọn phép gộp tường minh, không dùng Set.copyOf làm bộ hòa giải dữ liệu.

### 6.3. Map.copyOf không thấy lịch sử khóa đã bị ghi đè

staged.put("k",1) rồi staged.put("k",2) làm map nguồn chỉ còn một ánh xạ k→2. Map.copyOf(staged) nhận đúng trạng thái hiện tại ấy, nên không có hai ánh xạ k→1 và k→2 để kiểm tra với nhau.

Nếu yêu cầu là phát hiện khóa lặp trong một tệp cấu hình hoặc một dãy bản ghi, phải kiểm tra trong lúc đọc dãy đó, trước khi ghi đè làm mất thông tin. Không dựng HashMap bằng put rồi trông chờ copyOf phát hiện các lần xuất hiện cũ.

Với map có quy tắc khóa đặc biệt như IdentityHashMap, còn phải xem chính sách chuyển đổi quan hệ khóa. Map.copyOf không phải lời hứa giữ nguyên ngữ nghĩa so sánh theo danh tính của mọi loại map đầu vào.

### 6.4. Thứ tự in đã được chuẩn hóa có chủ đích

copiedSetSorted được in bằng new TreeSet<>(setCopy). Vì vậy [a,b] trong stdout là thứ tự của TreeSet dùng để trình bày, không phải cam kết rằng Set.copyOf giữ thứ tự chèn hoặc tự sắp xếp.

Set.of/Set.copyOf và Map.of/Map.ofEntries/Map.copyOf không phải API chọn thứ tự chèn. Muốn một thứ tự cho báo cáo hoặc kiểm thử, phải chọn cấu trúc/hợp đồng phù hợp hoặc so sánh dưới dạng tập/ánh xạ.

## 7. Mảng và varargs: phải xác định cái gì là một phần tử

### 7.1. Mảng tham chiếu có thể được dùng làm dãy đối số

Với String[] words, lời gọi List.of(words) thường lấy các String trong mảng làm phần tử thông qua cách gọi varargs. Nếu trong words có null, các phần tử được đưa vào list có null và lời gọi bị từ chối.

Muốn list có **một phần tử là chính mảng String[]**, có thể viết List.<String[]>of(words). Trong chương trình, mảng ấy không null nên phần tử cấp ngoài hợp lệ; một ô bên trong bằng null không bị kiểm tra đệ quy.

Đây là khác biệt về cách truyền dữ liệu và kiểu phần tử, không phải một ngoại lệ bí mật cho null.

### 7.2. Mảng nguyên thủy không tự biến thành list các số bọc

List.of(new int[]{1,2}) tạo list có một phần tử kiểu int[]. Nó không tự tạo List<Integer> gồm hai phần tử.

Vì vậy kiểm tra list.size() cho kết quả 1. Nếu muốn một list Integer từ các số trong mảng nguyên thủy, phải dùng một phép chuyển đổi phù hợp, chẳng hạn luồng số rồi boxed; không đọc List.of như thao tác trải mảng nguyên thủy tự động.

### 7.3. Mảng thông thường không so sánh nội dung bằng equals

row1 và row2 là hai String[] có cùng nội dung. Chúng là hai đối tượng mảng khác nhau và equals của mảng thông thường không so nội dung từng ô, nên Set.of(row1,row2) có kích thước 2.

Set.of(row1,row1) lại lặp đúng cùng một đối tượng và bị từ chối. Muốn quan hệ bằng nhau theo nội dung mảng, cần một kiểu dữ liệu/khóa định nghĩa điều đó phù hợp; gọi Arrays.equals ở một chỗ riêng không làm factory tự dùng phép so sánh ấy.

Quy tắc equals của [Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)) cùng các phép so sánh nội dung của [Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html) là hai cơ chế cần phân biệt.

## 8. Collector tạo kết quả chỉ đọc có quy tắc riêng

Một pipeline Stream có thể tạo dữ liệu không cho sửa bằng Collectors.toUnmodifiableList, toUnmodifiableSet và toUnmodifiableMap. Chúng cùng liên quan mục tiêu tạo kết quả chỉ đọc nhưng không có mọi quy tắc ngoại lệ giống lời gọi of trực tiếp.

### 8.1. Bảng đối chiếu collector

| Collector | null | Trùng | Thứ tự |
|---|---|---|---|
| toUnmodifiableList() | Từ chối phần tử null | Giữ phần tử trùng | Giữ thứ tự gặp phần tử nếu stream có thứ tự |
| toUnmodifiableSet() | Từ chối phần tử null | Gộp các phần tử bằng nhau, giữ đại diện tùy hợp đồng | Không cam kết thứ tự chèn |
| toUnmodifiableMap(keyMapper,valueMapper) | Từ chối khóa/giá trị null do các hàm ánh xạ trả về | Khóa trùng gây IllegalStateException | Không cam kết thứ tự chèn |
| toUnmodifiableMap(keyMapper,valueMapper,mergeFunction) | Vẫn không cho các hàm ánh xạ tạo khóa/giá trị null | Dùng mergeFunction xử lý các giá trị cùng khóa | Không cam kết thứ tự chèn |

Các hàm ánh xạ và hàm gộp được truyền vào cũng phải không null. Khi thiết kế phép gộp, phải đọc hợp đồng của nó, không dùng việc trả null như một cách tùy tiện giữ một ánh xạ có giá trị null.

Khác biệt nổi bật là **IllegalStateException của collector bản không có hàm gộp**, so với **IllegalArgumentException của Map.of/Map.ofEntries khi nhận khóa trùng**.

### 8.2. Chương trình thu Stream và đối chiếu factory cũ

Ví dụ ghi rõ từng nguồn Stream riêng, không dùng lại một stream đã kết thúc. Các map được in qua TreeMap khi cần stdout ổn định.

Tệp **CollectorFactoryRulesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorFactoryRulesDemo {
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
        System.out.println("collectedList=" + Stream.of("x", "x")
                .collect(Collectors.toUnmodifiableList()));
        System.out.println("collectedSetSize=" + Stream.of("x", "x")
                .collect(Collectors.toUnmodifiableSet()).size());

        expect("collectorListNull", NullPointerException.class,
                () -> Stream.of("x", null)
                        .collect(Collectors.toUnmodifiableList()));
        expect("collectorSetNull", NullPointerException.class,
                () -> Stream.of("x", null)
                        .collect(Collectors.toUnmodifiableSet()));
        expect("collectorDuplicateKey", IllegalStateException.class,
                () -> Stream.of("x", "x").collect(
                        Collectors.toUnmodifiableMap(Function.identity(), x -> 1)));
        expect("collectorNullKey", NullPointerException.class,
                () -> Stream.of("x").collect(
                        Collectors.toUnmodifiableMap(x -> (String) null, x -> 1)));
        expect("collectorNullValue", NullPointerException.class,
                () -> Stream.of("x").collect(
                        Collectors.toUnmodifiableMap(
                                Function.identity(), x -> (Integer) null)));

        Map<String, Integer> counts = Stream.of("red", "blue", "red").collect(
                Collectors.toUnmodifiableMap(
                        Function.identity(), x -> 1, Integer::sum));
        System.out.println("mergedCountsSorted=" + new TreeMap<>(counts));
        System.out.println("streamToListNull=" + Stream.of("x", null).toList());

        System.out.println("legacySingletonList=" +
                Collections.singletonList(null));
        System.out.println("legacySingletonSetHasNull=" +
                Collections.singleton(null).contains(null));
        Map<String, Integer> legacyMap =
                Collections.singletonMap(null, null);
        System.out.println("legacySingletonMap=" +
                legacyMap.size() + "," + legacyMap.containsKey(null));
        System.out.println("legacyNCopies=" + Collections.nCopies(2, null));
        List<String> nullableSource =
                new ArrayList<>(Arrays.asList("x", null));
        System.out.println("wrappedNullable=" +
                Collections.unmodifiableList(nullableSource));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectorFactoryRulesDemo.java
java CollectorFactoryRulesDemo
```

Stdout chính xác:

```text
collectedList=[x, x]
collectedSetSize=1
collectorListNull=NullPointerException
collectorSetNull=NullPointerException
collectorDuplicateKey=IllegalStateException
collectorNullKey=NullPointerException
collectorNullValue=NullPointerException
mergedCountsSorted={blue=1, red=2}
streamToListNull=[x, null]
legacySingletonList=[null]
legacySingletonSetHasNull=true
legacySingletonMap=1,true
legacyNCopies=[null, null]
wrappedNullable=[x, null]
```

### 8.3. Gộp khóa là một quyết định rõ ràng

Stream.of("x","x") với toUnmodifiableMap(identity,x→1) có hai phần tử ánh xạ tới cùng khóa x. Nó vẫn lỗi dù hai giá trị đều là 1; bản collector này không tự chấp nhận “trùng nhưng cùng giá trị”.

Trong phép đếm màu, mergeFunction là Integer::sum. Hai lần gặp red góp vào cùng khóa và được cộng thành 2. Đây là chính sách đếm có ý nghĩa rõ ràng, khác với âm thầm giữ một bản bất kỳ.

Tùy nghiệp vụ, có thể cần giữ một bản theo tiêu chí xác định, cộng dồn, thu các bản thành danh sách hoặc từ chối xung đột. Hàm gộp phải biểu đạt đúng ý định đó. Với pipeline có thể chạy song song, còn phải đáp ứng các điều kiện của phép thu và phép gộp; không dùng một hàm phụ thuộc thứ tự thực thi tùy ý.

Hợp đồng ở [Collectors.toUnmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function)) và các collector cùng họ là cơ sở để phân biệt kiểu ngoại lệ và chính sách trùng.

### 8.4. Stream.toList khác toUnmodifiableList về null

Stream.toList() có từ Java 16, trả list không cho sửa và trong ví dụ vẫn giữ null. Collectors.toUnmodifiableList() lại từ chối null.

Hai cách viết cùng có kết quả không cho sửa không có nghĩa đổi qua lại luôn giữ nguyên chính sách dữ liệu. Phải đọc hợp đồng phương thức đang dùng; đặc tả [Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) quy định cách thu list và không áp điều kiện từ chối null của toUnmodifiableList.

Collectors.toList() cũng là một phương thức khác nữa: không dùng nó làm cam kết chung về kiểu triển khai hoặc tính sửa được của kết quả. Nếu cần một ArrayList mutable một cách tường minh, chọn phép thu tạo cấu trúc đó theo hợp đồng.

## 9. Không áp quy tắc họ of cho mọi factory hoặc lớp bọc

### 9.1. Một số factory cũ cho phép null

Chương trình thứ ba cho thấy:

| API | Đầu vào trong ví dụ | Kết quả |
|---|---|---|
| Collections.singletonList(null) | Một phần tử null | List có một null |
| Collections.singleton(null) | Một phần tử null | Set có một null |
| Collections.singletonMap(null,null) | Khóa và giá trị null | Một ánh xạ có khóa null |
| Collections.nCopies(2,null) | Lặp cùng giá trị null hai lần | List có hai phần tử null |
| Collections.unmodifiableList(nullableSource) | Nguồn đã có null | View đọc lại phần tử null của nguồn |

Các factory/lớp bọc này không có cùng điều kiện đầu vào với List.of, Set.of và Map.of. Vì vậy “collection chỉ đọc không bao giờ có null” là một phát biểu sai nếu áp cho toàn bộ Java Collections.

Collections.nCopies cũng không nhân bản đối tượng phần tử. Nếu truyền một đối tượng mutable, các vị trí lặp cùng tham chiếu; điều này khác với tạo n đối tượng mutable riêng.

Hợp đồng của các phương thức thuộc [Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html) phải được đọc theo từng API, không thay bằng suy luận từ tên chung “factory”.

### 9.2. Lớp bọc không phải bộ lọc dữ liệu

Collections.unmodifiableList(source) chủ yếu chặn sửa qua giao diện được trả ra, không chủ động kiểm tra và loại null đã có trong source. Với Set hoặc Map, lớp bọc cũng dựa vào dữ liệu nguồn và chính sách vốn có của nguồn.

Nếu source là một ArrayList có các phần tử lặp, bọc unmodifiableList vẫn giữ các phần tử lặp. Nếu map nguồn đã ghi đè khóa trong lúc put, bọc nó không khôi phục lịch sử các bản ghi đã bị thay.

Bởi vậy, thay lớp bọc bằng copyOf có thể đổi chính sách null, quan hệ theo nguồn và thời điểm phát hiện lỗi. Không coi đó là một thay thế chỉ liên quan cách viết.

## 10. Chọn chính sách trước khi chọn phương thức

Hãy bắt đầu từ yêu cầu dữ liệu, thay vì chọn một factory bất kỳ rồi sửa lỗi cho đến khi chạy được:

1. Dữ liệu có được phép thiếu không, và thiếu được biểu diễn bằng null, không có phần tử/khóa, hay một giá trị cụ thể?
2. Phần tử trùng là có ý nghĩa, cần gộp, hay là lỗi?
3. Với map, khóa được chuẩn hóa theo quy tắc nào trước khi kiểm tra trùng?
4. Nếu hai bản có cùng khóa/mã nhưng khác nội dung, chính sách xung đột là gì?
5. Kết quả có cần thứ tự duyệt cụ thể không?
6. Cần ảnh chụp tách khỏi nguồn hay một view tiếp tục theo nguồn?

### 10.1. Không âm thầm xóa null nếu đó là lỗi dữ liệu

Lọc Objects::nonNull trước List.copyOf có thể là đúng nếu hợp đồng chủ ý bỏ các mục thiếu. Nó cũng có thể che mất một bản ghi sai mà người dùng cần được báo.

Tương tự, Set.copyOf có thể phù hợp với danh sách tag mà việc lặp lại không quan trọng, nhưng không phù hợp để kiểm tra rằng tệp khai báo không có mục lặp. Hai trường hợp có cùng đầu vào hình thức nhưng yêu cầu nghiệp vụ khác nhau.

Nếu cần lỗi với vị trí, tên trường hoặc mã bản ghi, kiểm tra và báo ở biên nhận dữ liệu. Thông báo lỗi mặc định của factory không phải một định dạng chẩn đoán nghiệp vụ được cam kết.

### 10.2. Ví dụ nhận Collection nhưng từ chối trùng có chủ đích

Nếu yêu cầu là tạo set không cho sửa, đồng thời đầu vào phải không null và không có phần tử trùng, có thể viết một phương thức riêng như sau.

Đây là phương thức đặt trong một lớp có import Collection, Set, LinkedHashSet và Objects; không phải chương trình main độc lập. Phần tử phải có equals/hashCode đúng và không thay đổi những thuộc tính liên quan trong lúc xử lý:

```java
static <T> Set<T> requireDistinct(Collection<? extends T> values) {
    Objects.requireNonNull(values, "values");
    Set<T> unique = new LinkedHashSet<>();
    int index = 0;
    for (T value : values) {
        Objects.requireNonNull(value, "null element at index " + index);
        if (!unique.add(value)) {
            throw new IllegalArgumentException("duplicate at index " + index);
        }
        index++;
    }
    return Set.copyOf(unique);
}
```

Phương thức kiểm tra từng giá trị trước khi tạo kết quả. Khi LinkedHashSet.add trả false, đã gặp phần tử bằng nhau trước đó nên báo lỗi thay vì gộp âm thầm.

LinkedHashSet ở đây là cấu trúc tạm để kiểm tra. Kết quả cuối dùng Set.copyOf nên **không cam kết thứ tự chèn**. Nếu hợp đồng yêu cầu giữ thứ tự, phải chọn cách trả cấu trúc/lớp bọc phù hợp thay vì gán thêm bảo đảm không có trong phương thức này.

Thông báo dùng chỉ số bắt đầu từ 0 để minh họa chẩn đoán. Ứng dụng thực tế có thể dùng số dòng hoặc tên trường, miễn hợp đồng rõ ràng. Đây không phải kiểm tra đệ quy các đối tượng con và cũng không làm phần tử mutable trở nên bất biến.

### 10.3. Với map, kiểm tra trước khi dữ liệu mất đi

Nếu đang xử lý một dãy entry và muốn từ chối khóa lặp, hãy kiểm tra ở bước thu dãy thành map. Map.ofEntries phù hợp khi đã có toàn bộ entry và muốn quy tắc từ chối khóa trùng của factory.

Với Stream, có thể dùng toUnmodifiableMap bản không có hàm gộp nếu kiểu lỗi đó phù hợp, hoặc tự cung cấp cơ chế báo xung đột theo nghiệp vụ. Nếu muốn gộp, dùng bản có hàm gộp với chính sách được xác định.

Một HashMap đã bị put ghi đè không còn đủ thông tin để biết trước đó có hai bản hay không. Việc gọi Map.copyOf sau cùng chỉ cố định trạng thái hiện có; không phải một bước kiểm toán toàn bộ dữ liệu thô.

## 11. Những điều các kiểm tra này không bảo đảm

### 11.1. Không kiểm tra mọi thuộc tính nghiệp vụ

List.of nhận "" vì chuỗi đó không null. Set.of có thể nhận "admin" và "ADMIN" vì chúng không equals. Map.of nhận một số âm làm giá trị nếu kiểu cho phép; nó không biết số đó có hợp lệ với hạn mức nghiệp vụ không.

Hợp lệ theo factory chỉ nói đã thỏa các điều kiện của factory. Nó không chứng minh mọi giá trị có ý nghĩa với ứng dụng.

### 11.2. Không tự sao chép sâu hoặc bảo vệ khóa mutable

Các factory lưu phần tử/khóa/giá trị theo hợp đồng của chúng, không tự nhân bản sâu mọi trạng thái bên trong. Một phần tử có thể đổi thuộc tính dù collection không cho thêm/xóa/thay vị trí.

Nếu phần tử của set hoặc khóa của map bị đổi các thuộc tính ảnh hưởng equals/hashCode khi đang được chứa, hành vi tra cứu có thể không còn đúng theo hợp đồng. Không cho sửa cấu trúc không tự cấm các setter của đối tượng khóa.

Chính sách phát hiện trùng vì thế dựa vào một quan hệ bằng nhau đúng và ổn định. Chọn khóa bất biến thường giúp giữ điều kiện đó.

### 11.3. Không tự làm nguồn đọc đồng thời trở nên nhất quán

copyOf tạo kết quả không theo các thay đổi cấu trúc về sau của nguồn, nhưng việc đọc nguồn để tạo kết quả vẫn cần hợp đồng phối hợp nếu nguồn bị nhiều luồng cập nhật.

Một dữ liệu đang thay đổi mà thiếu đồng bộ không được sửa bằng cách chỉ thêm copyOf ở cuối. Bài này dùng dữ liệu tuần tự để tập trung kiểm chứng chính sách null và trùng.

### 11.4. Không chọn thứ tự duyệt hoặc danh tính đối tượng theo nhu cầu

Không dùng thứ tự in của một Set.of trong một lần chạy làm bằng chứng về thứ tự chèn. Không dùng == trên các collection do factory trả về để kiểm tra “đã copy đúng”: factory có thể tái sử dụng đối tượng phù hợp theo hợp đồng.

Nếu cần kết quả thứ tự xác định cho hiển thị, chọn hoặc chuyển sang một mô hình có thứ tự được nêu rõ. Nếu cần so sánh tập phần tử, dùng quan hệ của Set; nếu cần so sánh dãy, dùng quan hệ của List với thứ tự tương ứng.

## 12. Phân biệt các lỗi và tránh dựa vào chi tiết triển khai

| Tình huống | Loại kết quả cần nhớ |
|---|---|
| null ở đầu vào bị List.of/Set.of/Map.of cấm | NullPointerException |
| Phần tử trùng ở Set.of | IllegalArgumentException |
| Khóa trùng ở Map.of/Map.ofEntries | IllegalArgumentException |
| Phần tử trùng ở List.of/List.copyOf | Hợp lệ, vẫn giữ các lần xuất hiện |
| Phần tử trùng ở Set.copyOf/toUnmodifiableSet | Hợp lệ, giữ một đại diện |
| Khóa trùng ở toUnmodifiableMap bản không có hàm gộp | IllegalStateException |
| Cố add/remove/put trên kết quả factory không cho sửa | UnsupportedOperationException |
| Giá trị lặp ở hai khóa Map khác nhau | Hợp lệ nếu các dữ liệu còn lại hợp lệ |

### 12.1. Không cam kết thứ tự phát hiện nhiều lỗi cùng lúc

Nếu một đầu vào vừa có null vừa có phần tử/khóa trùng, không viết kiểm thử chung cho mọi factory rồi yêu cầu một lỗi cụ thể luôn được phát hiện trước. Hợp đồng có thể không quy định thứ tự kiểm tra đó.

Các chương trình trong bài cô lập từng lỗi để kết luận rõ. Khi kiểm tra dữ liệu ứng dụng và cần thứ tự báo lỗi nhất quán, hãy tự thiết kế thứ tự kiểm tra ở biên dữ liệu.

### 12.2. Không phụ thuộc chuỗi thông báo hoặc tên lớp nội bộ

Thông báo của IllegalArgumentException hay IllegalStateException có thể chứa chi tiết hữu ích để gỡ lỗi, nhưng không nên được dùng như một giao thức phân tích dữ liệu ổn định giữa các phiên bản.

Tương tự, tên lớp nội bộ của list/set/map do JDK tạo không phải API để ứng dụng lựa chọn hành vi. Kiểm tra theo hợp đồng phương thức và loại ngoại lệ được quy định.

### 12.3. Không dùng contains(null) làm phép dò hợp lệ tổng quát

Việc collection không chứa null không tự bảo đảm contains(null) luôn trả false. Các API collection có quy tắc về đối số không được chấp nhận; một phép truy vấn như vậy có thể bị từ chối tùy hợp đồng.

Để kiểm tra collection đầu vào trước khi gọi factory, hãy kiểm tra từng phần tử theo chính sách của mình. Sau khi factory đã tạo kết quả hợp lệ với hợp đồng không null, không cần thử một truy vấn null để “xác nhận lại”.

## 13. Bài tập và lời giải

### Bài 1 — Cùng dữ liệu, khác factory

So sánh List.of("a","a"), Set.of("a","a") và Set.copyOf(List.of("a","a")).

**Lời giải:** List có hai phần tử a; Set.of gây IllegalArgumentException; Set.copyOf tạo set kích thước 1. “Không cho sửa” không quyết định chính sách đối với đầu vào trùng.

### Bài 2 — Giá trị Map lặp

Map.of("left",10,"right",10) có hợp lệ không? Map.of("left",10,"left",10) thì sao?

**Lời giải:** trường hợp đầu hợp lệ vì khóa khác nhau. Trường hợp sau gây IllegalArgumentException vì khóa lặp, dù giá trị giống nhau.

### Bài 3 — Null ở cấp nào?

So sánh List.of((String)null), List.of((String[])null) và List.<String[]>of(new String[]{null}).

**Lời giải:** hai trường hợp đầu gây NullPointerException; một trường hợp là phần tử null, trường hợp còn lại là mảng varargs null. Trường hợp thứ ba tạo list một phần tử là mảng không null, bên trong mảng có null. Factory không kiểm tra đệ quy mọi ô của phần tử mảng.

### Bài 4 — Entry chưa tạo xong

Trong Map.ofEntries(Map.entry("k",null)), lời gọi nào có thể báo lỗi trước?

**Lời giải:** Map.entry("k",null) gây NullPointerException khi được đánh giá để tạo đối số. Chưa có entry hợp lệ để truyền vào Map.ofEntries. Một entry lấy từ nguồn khác có khóa/giá trị null cũng sẽ bị ofEntries từ chối khi nó trích dữ liệu.

### Bài 5 — Hai đối tượng bằng nhau, khác mô tả

Hai Label khác tham chiếu có cùng id và equals/hashCode dựa trên id, nhưng khác text. Có thể dùng Set.copyOf rồi chắc chắn lấy được text của Label đầu tiên không?

**Lời giải:** không. Kết quả chỉ giữ một đại diện trong nhóm bằng nhau và không cam kết quy tắc “bản đầu thắng”. Nếu mô tả khác nhau cần được xử lý, phải định nghĩa phát hiện xung đột hoặc tiêu chí chọn bản.

### Bài 6 — Hash code giống nhau

Hai String khác nội dung có cùng hashCode. Có bắt buộc Set.of từ chối chúng không?

**Lời giải:** không. Trùng được xác định theo quan hệ bằng nhau, không phải chỉ theo hashCode. "FB" và "Ea" ở ví dụ cùng hash nhưng đều tồn tại trong set.

### Bài 7 — Lỗi phát hiện quá muộn

Đọc hai dòng cấu hình k=1, k=2 bằng hai lần put vào HashMap, rồi gọi Map.copyOf. Có nhận được lỗi khóa trùng từ hai dòng đầu vào không?

**Lời giải:** không thể dựa vào bước copyOf để phát hiện lịch sử ấy. Sau put lần hai, map chỉ giữ k=2. Phải kiểm tra khóa lặp lúc chuyển các dòng cấu hình thành map, trước khi thông tin bị ghi đè.

### Bài 8 — Collector có cùng giá trị

Stream có "x","x", dùng toUnmodifiableMap(identity,x→1) không có hàm gộp. Hai giá trị bằng nhau có làm collector chấp nhận không?

**Lời giải:** không. Khóa trùng gây IllegalStateException. Nếu muốn đếm số lần xuất hiện, có thể dùng hàm gộp cộng số đếm. Đó là một chính sách được viết rõ, không phải hành vi mặc định.

### Bài 9 — Thay Stream.toList bằng collector

Một stream có một phần tử null. Có thể đổi stream.toList() sang collect(toUnmodifiableList()) rồi mặc định chính sách dữ liệu không đổi không?

**Lời giải:** không. toUnmodifiableList từ chối null; ví dụ Stream.toList vẫn giữ null. Cả hai cho kết quả không sửa được nhưng điều kiện đầu vào khác nhau.

### Bài 10 — Chuyển từ singleton sang of

Code cũ dùng Collections.singletonMap(null,null). Có thể thay trực tiếp bằng Map.of(null,null) khi muốn viết ngắn hơn không?

**Lời giải:** không giữ nguyên hành vi. singletonMap của ví dụ cho phép ánh xạ đó; Map.of từ chối null. Trước khi thay cần xác định dữ liệu thiếu phải được biểu diễn và kiểm tra như thế nào.

### Bài 11 — Cùng nội dung mảng

a và b là hai int[] khác đối tượng, cùng chứa 1,2. Set.of(a,b) có bắt buộc xem chúng là trùng không?

**Lời giải:** không. Mảng thông thường dùng quan hệ bằng nhau theo danh tính đối tượng, không tự so nội dung. Lặp đúng cùng tham chiếu a hai lần lại là trùng. Nếu cần khóa/tập theo nội dung, hãy dùng một biểu diễn có equals/hashCode theo nội dung phù hợp.

### Bài 12 — Chuẩn hóa trước tạo Map

Hai mã "A" và "a" được coi là một mã sau bước chuyển sang chữ thường. Nếu tạo Map trực tiếp từ dữ liệu thô không báo trùng, đã chứng minh dữ liệu hợp lệ theo nghiệp vụ chưa?

**Lời giải:** chưa. Quan hệ khóa sau chuẩn hóa khác với equals trên dữ liệu thô. Cần chuẩn hóa theo chính sách xác định, rồi kiểm tra xung đột trên khóa đã chuẩn hóa trước khi cố định kết quả.

## 14. Cách tự kiểm chứng khi dùng factory trong dự án

Một bộ kiểm tra nhỏ nên tách các tình huống sau thành ca độc lập:

1. Đầu vào hợp lệ rỗng, một phần tử và nhiều phần tử.
2. Tham chiếu nguồn null đối với copyOf.
3. Phần tử null; riêng Map thử cả khóa null và giá trị null.
4. Phần tử/khóa bằng nhau nhưng khác tham chiếu.
5. Phần tử cùng hash nhưng không equals.
6. Giá trị Map lặp với các khóa khác nhau.
7. Chính sách trùng: từ chối, giữ mọi lần xuất hiện hay gộp.
8. Các trường hợp varargs/mảng nếu API của mình nhận mảng.
9. Không so thứ tự Set/Map trừ khi đã chọn hợp đồng thứ tự riêng.
10. Không dựa vào thứ tự phát hiện của một đầu vào cố ý có nhiều lỗi khác nhau.

Nếu dữ liệu có các đối tượng mutable, thêm kiểm tra về biến đổi thuộc tính hoặc chuyển sang giá trị bất biến theo nhu cầu. Nếu lấy từ nhiều luồng, kiểm tra cả thời điểm và tính nhất quán của việc tạo kết quả.

Các chương trình trong bài in tên ngoại lệ hoặc giá trị xác định để phân biệt hợp đồng, không dựa vào tên lớp nội bộ, thông báo lỗi hay thứ tự ngẫu nhiên của set/map.

## 15. Tài liệu đối chiếu

- [List — các factory of và copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
- [Set.copyOf — gộp phần tử trùng và chọn đại diện](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- [Map — of, ofEntries, entry và copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Collectors — các phép thu không cho sửa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Hướng dẫn tạo list, set và map không cho sửa](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html).
- [Collections — singleton, nCopies và các lớp bọc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).
