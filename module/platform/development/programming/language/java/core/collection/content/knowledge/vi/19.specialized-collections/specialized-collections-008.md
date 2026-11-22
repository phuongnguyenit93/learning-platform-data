# Enumeration và chuyển đổi sang Iterator hoặc List

## 1. Khi API cũ trả về một đối tượng dùng để duyệt

Một số API Java trả về `Enumeration<E>` thay vì List hoặc Iterator. Ví dụ, `Vector.elements()` cho phép lấy lần lượt các phần tử của Vector. Khi cần đưa dữ liệu đó vào mã dùng Iterator hoặc xử lý như một danh sách, trước hết phải xác định mình đang chuyển **cách duyệt** hay đang **thu dữ liệu thành một collection mới**.

`Enumeration` là một giao diện lấy tuần tự từng phần tử. Nó không phải nơi chứa toàn bộ dữ liệu theo hợp đồng của một List, cũng không phải từ khóa `enum` dùng để khai báo tập hằng.

Ba kết quả sau có ý nghĩa khác nhau:

| Đối tượng | Vai trò | Điều nên nghĩ đến |
|---|---|---|
| `Enumeration<E>` | Một lượt đọc tuần tự qua các phần tử | Còn gì chưa được lấy? |
| `Iterator<E>` | Giao diện duyệt phổ biến trong Collections Framework | Cách dùng hasNext/next và thao tác tùy chọn |
| `List<E>` | Collection chứa các phần tử theo vị trí | Lưu lại dữ liệu, xem theo chỉ số, tạo các lượt duyệt mới |

Chuyển từ Enumeration sang Iterator bằng `asIterator()` thích nghi giao diện của phần còn lại. Chuyển sang List bằng `Collections.list(...)` lấy hết phần còn lại để tạo một ArrayList mới. Cả hai đều không tự quay về phần tử đầu đã đọc.

Các chương trình đầy đủ trong bài dùng Java 17 trở lên. Phần adapter thủ công cuối bài còn được kiểm tra biên dịch với Java 8 để minh họa cách làm khi chưa có `Enumeration.asIterator()`.

## 2. Hợp đồng duyệt của Enumeration

### 2.1. Hai phương thức chính

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `hasMoreElements()` | boolean | Còn phần tử để lấy không? |
| `nextElement()` | E | Lấy phần tử tiếp theo và tiến lượt duyệt |

Gọi nextElement liên tiếp cho các phần tử liên tiếp. Khi đã hết, nextElement ném `NoSuchElementException`; nó không dùng null làm tín hiệu kết thúc.

Đoạn minh họa dưới đây đặt trong một phương thức đã có biến elements, không phải tệp Java độc lập:

```java
while (elements.hasMoreElements()) {
    String value = elements.nextElement();
    System.out.println(value);
}
```

Không gọi nextElement chỉ để kiểm tra còn dữ liệu hay không, vì mỗi lần gọi hợp lệ đều tiêu thụ một phần tử của lượt duyệt. Cũng không gọi nextElement hai lần cho cùng một vòng nếu chỉ muốn xử lý một phần tử: lần thứ hai sẽ đọc phần tử kế tiếp.

### 2.2. Một vị trí đọc đang tiến, không phải một collection tự lặp lại

Có thể hình dung nguồn có A, B, C và Enumeration đã trả A:

```text
Nguồn dữ liệu:       [A, B, C]
Đã đọc:              A
Phần còn lại:        B, C
Vị trí đọc tiếp:        ↑
```

Enumeration không có phương thức reset, get(index), size hoặc remove trong giao diện của nó. Nếu muốn duyệt lại từ đầu, cần một lượt duyệt mới do nguồn cung cấp, hoặc cần lưu các phần tử vào một collection riêng.

Việc duyệt hết Enumeration không đồng nghĩa xóa các phần tử khỏi Vector hay collection nguồn. **Trạng thái con trỏ duyệt** khác với **nội dung nguồn dữ liệu**.

### 2.3. Thứ tự và null phụ thuộc dữ liệu nguồn

Enumeration không tự sắp xếp hoặc loại phần tử trùng. Nó trả phần tử theo hợp đồng của API cung cấp nó. Với Vector trong các ví dụ, đó là thứ tự phần tử của Vector.

Một phần tử null có thể xuất hiện nếu nguồn cho phép. Vì vậy, mẫu dừng bằng `nextElement() == null` không đúng tổng quát: nó vừa làm tiến lượt duyệt, vừa có thể dừng ở một dữ liệu null hợp lệ. Dùng hasMoreElements để kiểm tra còn phần tử.

Tài liệu [Enumeration — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html) là nguồn đối chiếu các quy tắc này.

## 3. Chương trình 1: một lượt duyệt cơ bản

Lưu chương trình đầy đủ vào `EnumerationBasicsDemo.java`. Vector được dùng ở đây để minh họa một API thực sự trả Enumeration.

```java
import java.util.Arrays;
import java.util.Enumeration;
import java.util.NoSuchElementException;
import java.util.Vector;

public class EnumerationBasicsDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("alpha", "beta", "gamma"));
        Enumeration<String> elements = source.elements();
        int count = 0;
        while (elements.hasMoreElements()) {
            String value = elements.nextElement();
            System.out.println("value=" + value);
            count++;
        }
        System.out.println("count=" + count);
        System.out.println("hasMore=" + elements.hasMoreElements());
        System.out.println("sourceSize=" + source.size());
        try {
            elements.nextElement();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("exhaustedNext=NoSuchElementException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumerationBasicsDemo.java
java EnumerationBasicsDemo
```

Stdout:

```text
value=alpha
value=beta
value=gamma
count=3
hasMore=false
sourceSize=3
exhaustedNext=NoSuchElementException
```

### 3.1. Đọc hết không làm nguồn rỗng

Ba vòng lặp lấy alpha, beta, gamma. count bằng 3 và hasMore sau đó là false, nhưng sourceSize vẫn là 3. Không có thao tác xóa nào được gọi.

nextElement sau khi hết ném `NoSuchElementException`, đúng hợp đồng. Không được viết logic dựa trên kỳ vọng nó trả một giá trị cuối đặc biệt.

Nếu cần đọc lại chính Vector, có thể gọi source.elements() để nhận một Enumeration mới của dữ liệu nguồn khi đó. Lấy một biến khác trỏ vào Enumeration cũ không làm vị trí đọc quay lại.

## 4. Enumeration và Iterator khác nhau như thế nào?

| Enumeration | Iterator | Nhận xét |
|---|---|---|
| `hasMoreElements()` | `hasNext()` | Kiểm tra còn phần tử |
| `nextElement()` | `next()` | Lấy và tiến tới phần tử tiếp theo |
| Không có remove | `remove()` là thao tác tùy chọn | Không phải mọi Iterator đều xóa được |
| Có `asIterator()` từ Java 9 | Có `forEachRemaining()` từ Java 8 | Giúp kết nối các API dùng giao diện khác nhau |

Enumeration và Iterator đều không tự trở thành Iterable. Chuyển sang Iterator cho phép dùng hasNext/next hoặc forEachRemaining, nhưng không vì vậy mà một biến Iterator dùng trực tiếp được ở mọi vòng for-each yêu cầu Iterable.

Nếu viết API mới cần cung cấp khả năng duyệt, thường nên chọn các giao diện phù hợp của Collections Framework thay vì tạo thêm một API Enumeration không cần thiết. Còn khi nhận Enumeration từ API đã có, có thể thích nghi tại ranh giới dùng nó.

## 5. Chuyển sang Iterator bằng asIterator

### 5.1. Duyệt phần còn lại, không tạo bản sao toàn bộ

Với Java 9 trở lên, gọi `elements.asIterator()` để nhận Iterator duyệt các phần tử còn lại mà Enumeration bao phủ. Java 17 hỗ trợ phương thức này.

Phần triển khai mặc định ánh xạ hasNext sang hasMoreElements, next sang nextElement. Nó không đọc trước toàn bộ dữ liệu thành một List mới. Nếu trước đó đã lấy A thì Iterator tiếp tục từ B.

### 5.2. Không dùng xen kẽ Enumeration gốc sau khi thích nghi

API quy định kết quả duyệt không xác định nếu tiếp tục gọi phương thức trên Enumeration sau lời gọi asIterator. Vì vậy, sau khi tạo adapter, phần mã sử dụng phải tiếp tục qua Iterator, không xen `elements.nextElement()` hay trực tiếp kiểm tra Enumeration gốc.

Đừng xem Enumeration và Iterator kết quả là hai con trỏ độc lập. Cũng đừng tạo nhiều adapter từ cùng Enumeration rồi giả định mỗi adapter có thể đọc một bản dữ liệu riêng từ đầu.

Trong chương trình tiếp theo, có một lần đọc Enumeration trước asIterator; sau thời điểm thích nghi, mọi thao tác duyệt đều qua Iterator. Việc xem nội dung Vector nguồn không phải lời gọi lại vào Enumeration.

### 5.3. Iterator kết quả không tự có quyền xóa

Phần triển khai mặc định của asIterator tạo Iterator có remove ném `UnsupportedOperationException`. Enumeration không cung cấp một thao tác xóa để adapter có thể tự chuyển tiếp.

Điều đó vẫn đúng với adapter mặc định khi dữ liệu nguồn là một Vector có thể sửa. Khả năng sửa của collection nguồn không đồng nghĩa mọi lượt duyệt bọc quanh nó đều cho xóa.

`Iterator.remove` nói chung là thao tác tùy chọn. Muốn xóa trong quá trình duyệt, cần một Iterator mà API nguồn thật sự hỗ trợ thao tác đó và phải tuân theo vòng đời next/remove. Không ép quyền xóa vào một adapter bằng cách đoán cách sửa collection phía sau.

## 6. Chương trình 2: thích nghi phần còn lại

Lưu vào `EnumerationIteratorDemo.java`:

```java
import java.util.Arrays;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.NoSuchElementException;
import java.util.Vector;

public class EnumerationIteratorDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("A", "B", "C"));
        Enumeration<String> elements = source.elements();
        System.out.println("beforeAdapt=" + elements.nextElement());
        Iterator<String> iterator = elements.asIterator();
        System.out.println("iteratorHasNext=" + iterator.hasNext());
        System.out.println("iteratorNext=" + iterator.next());
        try {
            iterator.remove();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("remove=UnsupportedOperationException");
        }
        iterator.forEachRemaining(value -> System.out.println("remaining=" + value));
        System.out.println("iteratorHasNextAfter=" + iterator.hasNext());
        System.out.println("sourceAfterTraversal=" + source);
        try {
            iterator.next();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("exhaustedIteratorNext=NoSuchElementException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumerationIteratorDemo.java
java EnumerationIteratorDemo
```

Stdout:

```text
beforeAdapt=A
iteratorHasNext=true
iteratorNext=B
remove=UnsupportedOperationException
remaining=C
iteratorHasNextAfter=false
sourceAfterTraversal=[A, B, C]
exhaustedIteratorNext=NoSuchElementException
```

### 6.1. A đã được đọc trước khi thích nghi

`beforeAdapt=A` đến từ nextElement gọi trước asIterator. Iterator bắt đầu với B, nên iteratorNext in B, rồi forEachRemaining xử lý C. Không có việc A được phát lại.

hasNext sau khi duyệt là false. Gọi next trên Iterator hết cũng ném `NoSuchElementException`. Source vẫn `[A, B, C]` vì duyệt không loại dữ liệu.

### 6.2. Phương thức remove bị từ chối

Lời gọi remove đặt sau một next hợp lệ nhưng vẫn ném `UnsupportedOperationException`, vì adapter mặc định không hỗ trợ xóa. Đây khác với trường hợp một Iterator có hỗ trợ remove nhưng người dùng gọi sai vòng đời.

forEachRemaining chỉ là cách xử lý phần còn lại tiện hơn một vòng while. Nó không tự tạo một bộ lưu dữ liệu và không tự cung cấp khả năng duyệt lại sau đó.

## 7. Chuyển sang List bằng Collections.list

### 7.1. Thu hết phần còn lại vào một ArrayList mới

`Collections.list(elements)` trả một `ArrayList<E>` chứa các phần tử Enumeration còn trả được, theo đúng thứ tự chúng được lấy ra. Phương thức cần duyệt nguồn đến hết để hoàn thành danh sách.

Đoạn minh họa bên trong một phương thức đã có Enumeration<String>:

```java
ArrayList<String> items = Collections.list(elements);
```

Có thể khai báo kết quả bằng `List<String>` nếu chỉ cần giao diện List. Kiểu đối tượng được API trả về vẫn là ArrayList.

Danh sách kết quả không tự có các phần tử đã đọc trước đó. Với nguồn A,B,C và A đã được lấy, list chỉ thu B,C. Nếu Enumeration đã hết, kết quả là ArrayList rỗng.

Hợp đồng tại [Collections.list — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html) bảo đảm thứ tự phần tử theo Enumeration. Nó không tự sắp thứ tự chữ cái, không khử trùng và không quay lại nguồn để đọc một lượt mới.

### 7.2. Trạng thái Enumeration bị tiêu thụ, dữ liệu nguồn không bị xóa

Collections.list phải gọi các thao tác duyệt để thu phần tử. Vì vậy Enumeration đã đi đến cuối sau khi phương thức hoàn thành bình thường trên một nguồn hữu hạn.

Điều đó không tương đương remove khỏi collection nguồn. Nếu Enumeration đọc một Vector, các phần tử của Vector vẫn có thể còn nguyên; chỉ lượt duyệt đã bị tiêu thụ.

Lấy list hai lần liên tiếp từ cùng Enumeration không tạo hai bản giống nhau: lần đầu lấy phần còn lại, lần sau thường chỉ có phần rỗng vì lượt duyệt đã hết. Nếu cần nhiều nơi cùng dùng dữ liệu đã thu, giữ List kết quả và tạo các Iterator của List khi cần.

### 7.3. Kết quả có thể sửa cấu trúc, nhưng không sao chép sâu phần tử

ArrayList mới có thể add, remove hoặc set theo hợp đồng của nó. Các thay đổi cấu trúc hay thay tham chiếu phần tử trong list mới không tự sửa Vector nguồn.

Tuy nhiên, phương thức sao chép các tham chiếu phần tử; không nhân bản sâu từng đối tượng. Nếu phần tử là một StringBuilder có thể thay đổi, source và list mới có thể cùng nhìn thấy thay đổi trên chính đối tượng đó.

Ba câu hỏi cần tách biệt:

1. Danh sách chứa có phải cấu trúc mới không? Có.
2. Các phần tử bên trong có được nhân bản sâu không? Không.
3. Việc thu list có khôi phục Enumeration từ đầu không? Không.

### 7.4. Null và phần tử trùng được giữ

Nếu Enumeration trả B,B,C, danh sách có hai vị trí mang B. Nếu nguồn trả một phần tử null hợp lệ, ArrayList kết quả giữ null ở vị trí tương ứng. Chuyển sang List không tự áp dụng chính sách loại null hoặc duy nhất hóa dữ liệu.

Phải phân biệt phần tử null với bản thân biến Enumeration là null. Một Enumeration hợp lệ có thể trả null; còn truyền một tham chiếu Enumeration null không phải cách yêu cầu một danh sách rỗng.

## 8. Chương trình 3: phần còn lại, bản sao nông và null

Lưu chương trình đầy đủ vào `EnumerationListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Vector;

public class EnumerationListDemo {
    public static void main(String[] args) {
        Vector<String> source = new Vector<>(Arrays.asList("A", "B", "B", "C"));
        Enumeration<String> elements = source.elements();
        System.out.println("consumedBeforeCopy=" + elements.nextElement());
        ArrayList<String> remaining = Collections.list(elements);
        System.out.println("remainingCopy=" + remaining);
        System.out.println("sourceHasMore=" + elements.hasMoreElements());
        remaining.set(0, "B2");
        remaining.add("D");
        System.out.println("modifiedCopy=" + remaining);
        System.out.println("unchangedSource=" + source);
        System.out.println("freshFullCopy=" + Collections.list(source.elements()));
        System.out.println("copyOfExhausted=" + Collections.list(elements));

        Vector<String> nullable = new Vector<>(Arrays.asList("x", null, "y"));
        ArrayList<String> nullCopy = Collections.list(nullable.elements());
        System.out.println("nullCopy=" + nullCopy);
        System.out.println("nullCopySize=" + nullCopy.size());

        Vector<StringBuilder> builders = new Vector<>();
        builders.add(new StringBuilder("shared"));
        ArrayList<StringBuilder> shallow = Collections.list(builders.elements());
        shallow.get(0).append("!");
        System.out.println("mutableSourceValue=" + builders.get(0));
        System.out.println("sameElementReference=" + (builders.get(0) == shallow.get(0)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumerationListDemo.java
java EnumerationListDemo
```

Stdout:

```text
consumedBeforeCopy=A
remainingCopy=[B, B, C]
sourceHasMore=false
modifiedCopy=[B2, B, C, D]
unchangedSource=[A, B, B, C]
freshFullCopy=[A, B, B, C]
copyOfExhausted=[]
nullCopy=[x, null, y]
nullCopySize=3
mutableSourceValue=shared!
sameElementReference=true
```

### 8.1. Chỉ B,B,C được thu vào bản sao đầu

`consumedBeforeCopy=A` lấy phần tử A trước lời gọi list. Vì vậy `remainingCopy=[B, B, C]`, giữ cả hai lần B. `sourceHasMore=false` xác nhận Enumeration đã được duyệt hết.

Đổi phần tử đầu của remaining thành B2 rồi thêm D tạo `[B2, B, C, D]`. Vector nguồn vẫn `[A, B, B, C]`; không có xóa hoặc set nào được chuyển ngược vào nó.

### 8.2. Lượt duyệt mới khác với dùng lại lượt đã hết

`Collections.list(source.elements())` nhận Enumeration mới từ Vector đang giữ dữ liệu, nên `freshFullCopy` có đủ A,B,B,C. `Collections.list(elements)` trên Enumeration cũ đã hết cho `copyOfExhausted=[]`.

Điểm khác biệt nằm ở đối tượng cung cấp lượt duyệt, không phải việc đổi tên biến kết quả. Nếu nguồn đã thay đổi trước khi tạo Enumeration mới, lượt mới đọc dữ liệu nguồn theo hợp đồng tại thời điểm đó; không mặc nhiên là một bản lịch sử của lần trước.

### 8.3. Phần tử null không kết thúc lượt đọc

`nullCopy=[x, null, y]` và size bằng 3 cho thấy null ở giữa không khiến quá trình thu dừng trước y. Đây là lý do dùng hasMoreElements làm điều kiện còn dữ liệu.

### 8.4. Cấu trúc mới vẫn chia sẻ một đối tượng mutable

Phần cuối tạo một Vector có StringBuilder mang nội dung shared. Collections.list tạo ArrayList mới, nhưng phần tử đầu vẫn là cùng StringBuilder. Append dấu chấm than qua list làm nguồn đọc được `shared!`.

`sameElementReference=true` giải thích kết quả đó. Một danh sách mới không đồng nghĩa toàn bộ cây đối tượng bên trong đã được sao chép. Nếu dữ liệu cần độc lập sâu, cách sao chép phải được thiết kế theo kiểu phần tử.

## 9. Chọn Iterator hay List theo công việc tiếp theo

| Nhu cầu | Cách xử lý | Ảnh hưởng chính |
|---|---|---|
| Xử lý tuần tự đúng phần còn lại một lần | Duyệt Enumeration trực tiếp hoặc thích nghi Iterator | Không bắt buộc giữ toàn bộ phần tử |
| Đưa vào API nhận Iterator | `asIterator()` trên Java 9+ | Thích nghi lượt duyệt còn lại |
| Cần size, truy cập theo vị trí hoặc duyệt nhiều lần | `Collections.list(...)` | Thu hết phần còn lại thành ArrayList mới |
| Cần vừa giữ dữ liệu vừa có Iterator | Thu List trước, rồi lấy Iterator từ List | Có dữ liệu chứa để tạo các lượt duyệt riêng |
| API cũ yêu cầu Enumeration nhưng đầu vào là Collection | `Collections.enumeration(collection)` | Cầu nối theo chiều ngược |

Đừng thu một List lớn chỉ để gọi forEach một lần nếu không có nhu cầu giữ dữ liệu. Ngược lại, đừng truyền cùng một lượt Enumeration đi nhiều nơi rồi kỳ vọng mỗi nơi nhận toàn bộ dữ liệu từ đầu.

Trong trường hợp vừa cần lưu vừa cần Iterator, đoạn minh họa là:

```java
// Minh họa, source là Enumeration<String> chưa được thích nghi.
List<String> items = Collections.list(source);
Iterator<String> firstPass = items.iterator();
Iterator<String> secondPass = items.iterator();
```

Hai Iterator của ArrayList có vị trí duyệt riêng trên cùng danh sách. Chúng không đến từ hai lần gọi asIterator trên Enumeration ban đầu. Danh sách vẫn có thể thay đổi nên các quy tắc sửa nguồn khi duyệt của nó vẫn phải được tôn trọng.

### 9.1. Chi phí thu dữ liệu

Nếu còn n phần tử, Collections.list phải lấy n phần tử và dành cấu trúc chứa các tham chiếu tương ứng. Ngoài công việc tuyến tính để xây danh sách, còn có chi phí của chính nguồn mỗi lần cung cấp phần tử.

Enumeration không công bố size trong giao diện và có thể lấy dữ liệu theo cơ chế riêng của API nguồn. Khi nguồn lớn, chỉ chọn thu toàn bộ nếu công việc cần nó. Với một nguồn không kết thúc, thao tác cố thu tất cả cũng không thể hoàn thành theo cách của một danh sách hữu hạn.

Adapter Iterator không tự nạp trước toàn bộ n phần tử. Nó phù hợp cho xử lý từng phần tử nhưng không biến nguồn thành nơi có thể tua lại.

### 9.2. Không ép kiểu để giả làm chuyển đổi

Một đối tượng Enumeration không tự triển khai Iterator hoặc List chỉ vì các kiểu này đều liên quan đến duyệt. Ép kiểu chỉ kiểm tra/khẳng định loại đối tượng, không tạo adapter và không thu dữ liệu. Nếu đối tượng không thực hiện giao diện đích, việc ép kiểu có thể gây ClassCastException.

Dùng asIterator hoặc Collections.list thể hiện đúng hành động cần thực hiện và cho phép người đọc đánh giá ảnh hưởng lên phần còn lại của lượt duyệt.

## 10. Chiều ngược: Collection sang Enumeration

Khi một thư viện cũ yêu cầu Enumeration, `Collections.enumeration(collection)` tạo cầu nối từ một Collection có sẵn. Ví dụ một List đang lưu tên có thể được đưa vào API cũ bằng một Enumeration tương ứng.

Đây là một lựa chọn tại ranh giới giữa hai API. Không cần đổi toàn bộ mô hình dữ liệu của chương trình về Vector chỉ để có kiểu trả về Enumeration.

Phương thức enumeration không có hợp đồng tạo một bản sao sâu hay đóng băng dữ liệu nguồn. Nếu cần một cấu trúc chứa độc lập trước khi đưa cho mã khác, hãy tạo bản sao collection một cách tường minh, rồi mới tạo Enumeration từ bản sao đó. Thứ tự và quy tắc thay đổi nguồn trong khi duyệt vẫn cần đọc theo collection/API thực tế.

Với List, lượt duyệt theo thứ tự danh sách. Cầu nối không tự sắp xếp, loại trùng hay bỏ null. Một Iterator có sẵn không phải là đối số Collection: cần xem API đầu vào thật sự đang có dữ liệu chứa hay chỉ còn một lượt đọc.

## 11. Adapter thủ công khi cần tương thích Java 8

### 11.1. Chuyển tiếp hai thao tác đọc

`Enumeration.asIterator()` được thêm từ Java 9. Nếu mã phải biên dịch cho Java 8, có thể tạo một Iterator chuyển tiếp hasNext sang hasMoreElements và next sang nextElement.

Adapter này chỉ bọc lượt đọc; nó không tạo một List. Cần dùng một đường duyệt nhất quán qua adapter sau khi đã chuyển quyền sử dụng, tránh các nơi khác cùng tiêu thụ Enumeration gốc làm mất phần tử mà bên đọc chưa biết.

Chương trình tiếp theo kiểm tra tham chiếu nguồn bằng Objects.requireNonNull ngay khi tạo adapter. Khi nguồn null, lỗi được phát hiện tại ranh giới chuyển đổi. Một nguồn hợp lệ nhưng rỗng vẫn là tình huống bình thường.

### 11.2. Nhận nguồn chỉ cung cấp phần tử

Khai báo `Enumeration<? extends T>` có nghĩa nguồn có thể cung cấp một kiểu con của T. Enumeration chỉ trả dữ liệu theo giao diện của nó; adapter không đưa thêm phần tử vào nguồn.

Vì Integer là Number, phương thức trong ví dụ có thể tạo `Iterator<Number>` từ `Enumeration<Integer>`. Các đối tượng trả về vẫn là Integer ban đầu. Generic không nhân bản phần tử hoặc chuyển Integer thành một loại số khác.

Không cần dùng kiểu raw hay ép kiểu không kiểm tra để viết cầu nối này. Nếu API cũ trả một Enumeration raw, generic ở phía nhận không tự kiểm chứng được mọi đối tượng bên trong; cần kiểm tra và xử lý kiểu thực tế theo hợp đồng của API đó.

### 11.3. Không cài remove đồng nghĩa dùng mặc định của Iterator

Lớp vô danh chỉ cài hasNext và next. Nó kế thừa remove mặc định của Iterator, nên thao tác xóa ném UnsupportedOperationException. Đừng viết remove rỗng để giả vờ thành công: mã gọi sẽ hiểu nhầm dữ liệu đã được xóa.

Nếu thực sự cần xóa từ collection, hãy dùng cơ chế được collection đó hỗ trợ. Không thể suy ra thao tác xóa đúng chỉ từ giao diện Enumeration.

## 12. Chương trình 4: cầu nối, generic và nguồn rỗng

Lưu chương trình đầy đủ vào `EnumerationCompatibilityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class EnumerationCompatibilityDemo {
    static <T> Iterator<T> adapt(Enumeration<? extends T> source) {
        Objects.requireNonNull(source, "source");
        return new Iterator<T>() {
            @Override
            public boolean hasNext() {
                return source.hasMoreElements();
            }

            @Override
            public T next() {
                return source.nextElement();
            }
        };
    }

    public static void main(String[] args) {
        List<String> modern = new ArrayList<>(Arrays.asList("red", "blue"));
        Enumeration<String> forLegacy = Collections.enumeration(modern);
        ArrayList<String> copyBack = Collections.list(forLegacy);
        modern.clear();
        System.out.println("copyBack=" + copyBack);
        System.out.println("modernSizeAfterClear=" + modern.size());

        Enumeration<Integer> integers =
                Collections.enumeration(Arrays.asList(10, 20));
        Iterator<Number> numbers = adapt(integers);
        System.out.println("number=" + numbers.next());
        try {
            numbers.remove();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("compatRemove=UnsupportedOperationException");
        }
        numbers.forEachRemaining(number -> System.out.println("number=" + number));
        System.out.println("hasNextAfter=" + numbers.hasNext());
        ArrayList<String> emptyCopy =
                Collections.list(Collections.<String>emptyEnumeration());
        emptyCopy.add("later");
        System.out.println("mutableEmptyCopy=" + emptyCopy);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumerationCompatibilityDemo.java
java EnumerationCompatibilityDemo
```

Stdout:

```text
copyBack=[red, blue]
modernSizeAfterClear=0
number=10
compatRemove=UnsupportedOperationException
number=20
hasNextAfter=false
mutableEmptyCopy=[later]
```

### 12.1. Bản thu List tồn tại độc lập với cấu trúc nguồn

modern ban đầu là List chứa red và blue. Collections.enumeration tạo lượt đọc để Collections.list thu thành một ArrayList khác. Sau khi đã thu xong, clear modern làm kích thước nguồn thành 0, nhưng copyBack vẫn chứa red và blue.

Ví dụ không sửa nguồn khi Enumeration còn đang được sử dụng. Nó minh họa tính độc lập của cấu trúc List đã thu, không chứng minh rằng mọi Enumeration là ảnh chụp cố định của nguồn.

### 12.2. Adapter chỉ thay giao diện đọc

Enumeration<Integer> cho hai số 10, 20. Iterator<Number> nhận được từ adapt lấy số 10 bằng next; remove bị từ chối; forEachRemaining tiếp tục với 20. hasNext sau đó là false.

Lời gọi remove đặt ngay sau next và trước forEachRemaining để thử đúng trường hợp adapter không hỗ trợ xóa. Không dùng ví dụ này làm mẫu gọi remove sau khi forEachRemaining đã chạy: hợp đồng Iterator không quy định hành vi remove trong tình huống đó.

### 12.3. Danh sách rỗng thu được vẫn có thể thêm phần tử

Collections.emptyEnumeration cung cấp một Enumeration rỗng. Collections.list từ nó trả một ArrayList rỗng có thể sửa. Thêm later vào danh sách cho kết quả `[later]`; thao tác không làm Enumeration có thêm dữ liệu.

Nguồn rỗng, nguồn null và nguồn đã đọc hết là ba điều cần phân biệt. Hai trường hợp có Enumeration hợp lệ đều có thể tạo List rỗng; tham chiếu null cần được xử lý như lỗi đầu vào hoặc theo chính sách tường minh của chương trình.

Chương trình này được biên dịch và chạy với mức API Java 17 như lệnh đã ghi. Cùng mã nguồn còn được kiểm tra biên dịch thành công với `--release 8`; nó không dùng asIterator.

## 13. Khi dữ liệu nguồn thay đổi trong lúc duyệt

### 13.1. Enumeration không bảo đảm chung về fail-fast

Không suy ra mọi Enumeration sẽ ném ConcurrentModificationException nếu nguồn đổi. Giao diện Enumeration không cung cấp một chính sách phát hiện sửa đổi áp dụng cho mọi triển khai.

Đặc biệt, [Vector — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html) nêu rằng Enumeration từ Vector không có cơ chế fail-fast. Nếu Vector bị thay đổi cấu trúc sau khi Enumeration được tạo, kết quả liệt kê không được xác định theo hợp đồng đó.

Vì vậy, không lấy một lần chạy tình cờ vẫn in được vài phần tử làm bằng chứng rằng vừa add/remove Vector vừa đọc Enumeration là an toàn. Các ví dụ đầy đủ ở trên giữ cấu trúc nguồn ổn định trong mỗi lượt duyệt đang hoạt động.

### 13.2. Bọc sang Iterator không tạo thêm bảo đảm đồng thời

asIterator không tự thay đổi chính sách của nguồn thành một chính sách an toàn cho nhiều luồng. Một Iterator được tạo từ Enumeration cũng không tự có cơ chế phát hiện mọi sửa đổi như Iterator riêng do một collection khác cung cấp.

Tương tự, Collections.list chỉ thu dữ liệu bằng các thao tác đọc. Nếu cần một bản dữ liệu nhất quán khi nhiều nơi có thể sửa nguồn, phải phối hợp việc đọc và sửa theo hợp đồng đồng bộ của nguồn. Gọi một hàm chuyển đổi không thay thế việc phối hợp đó.

Việc Vector đồng bộ một số thao tác riêng lẻ không có nghĩa toàn bộ chuỗi kiểm tra còn phần tử rồi lấy phần tử trở thành một giao dịch nguyên khối. Không dùng sự hiện diện của Vector làm lý do bỏ qua thiết kế truy cập đồng thời.

### 13.3. Bản sao List không phải cam kết bất biến

Sau khi thu xong trong điều kiện nguồn hợp lệ, List mới có cấu trúc chứa riêng. Nó vẫn là ArrayList có thể sửa và vẫn có thể chia sẻ các đối tượng phần tử có thể thay đổi.

Nếu yêu cầu là “đọc lại nhiều lần cùng một tập tham chiếu”, bản sao List thường phù hợp. Nếu yêu cầu là “mọi trạng thái của từng đối tượng phải giữ nguyên”, còn cần một thiết kế bất biến hoặc sao chép phần tử riêng; Collections.list không giải quyết yêu cầu đó.

## 14. Những lỗi dễ gặp

| Cách hiểu hoặc cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Xem Enumeration như nơi lưu dữ liệu có size/index | Giao diện chỉ cung cấp lượt đọc tuần tự | Thu List nếu cần thao tác theo vị trí |
| Dùng null làm dấu kết thúc | Null có thể là một phần tử hợp lệ | Kiểm tra hasMoreElements |
| Gọi nextElement hai lần trong một vòng cho một phần tử | Hai lần gọi tiêu thụ hai phần tử | Lấy một lần, giữ trong biến rồi dùng |
| Mong asIterator đọc lại phần đã lấy | Adapter tiếp tục phần còn lại | Tạo lượt mới từ nguồn hoặc lưu dữ liệu trước |
| Dùng trực tiếp Enumeration gốc sau asIterator | API không quy định kết quả duyệt của cách dùng đó | Tiếp tục duyệt qua Iterator |
| Ép Enumeration thành List | Ép kiểu không thu dữ liệu | Dùng Collections.list |
| Gọi Collections.list hai lần trên cùng lượt đã hết | Lần sau không có dữ liệu cũ để đọc lại | Giữ List đầu tiên hoặc xin lượt mới |
| Cho rằng adapter mặc định hỗ trợ remove vì nguồn sửa được | Enumeration không có thao tác xóa để chuyển tiếp | Dùng API xóa được hỗ trợ thực sự |
| Xem ArrayList mới như bản sao sâu | Phần tử có thể còn cùng tham chiếu | Thiết kế sao chép theo loại phần tử nếu cần |
| Mong đổi sang Iterator sẽ phát hiện mọi sửa đổi nguồn | Wrapper không thêm hợp đồng đó | Tuân theo chính sách của nguồn |
| Chọn thu toàn bộ mà không xét kích thước nguồn | Giữ thêm mọi tham chiếu của phần còn lại | Chọn duyệt tuần tự nếu công việc chỉ cần một lượt |
| Gọi asIterator trong mã phải biên dịch Java 8 | Phương thức có từ Java 9 | Dùng adapter tương thích hoặc nâng mức Java |

## 15. Tự kiểm tra

1. **Enumeration khác enum ở điểm nào?** Enumeration là giao diện duyệt tuần tự các phần tử; enum là cơ chế ngôn ngữ khai báo kiểu tập hằng.
2. **Nguồn có A,B,C, đã gọi nextElement lấy A. Collections.list nhận được gì?** B,C theo thứ tự đó, nếu nguồn giữ ổn định và lượt duyệt còn đúng hai phần tử này.
3. **Thu List có làm Vector nguồn rỗng không?** Không. Nó tiêu thụ lượt duyệt, không gọi xóa dữ liệu nguồn.
4. **Sau asIterator, có nên tiếp tục gọi hasMoreElements trên Enumeration gốc không?** Không. API Enumeration không quy định kết quả duyệt khi tiếp tục gọi trực tiếp phương thức trên Enumeration sau khi thích nghi.
5. **asIterator có cung cấp hai lượt độc lập nếu giữ cả hai biến không?** Không có bảo đảm đó. Dùng Iterator để tiếp tục phần còn lại; nếu cần các lượt riêng, thu vào List rồi lấy các Iterator của List.
6. **Collections.list tạo loại đối tượng gì?** ArrayList mới, có thể khai báo biến nhận là List; phần tử được giữ theo tham chiếu chứ không được sao chép sâu.
7. **Một nguồn trả x,null,y có khiến quá trình thu dừng tại null không?** Không. Khi null là phần tử hợp lệ, cả ba vị trí được đưa vào ArrayList.
8. **Vì sao adapter thủ công có thể trả Iterator<Number> từ Enumeration<Integer>?** Nguồn chỉ cần cung cấp các đối tượng thuộc Number; Integer thỏa mãn quan hệ đó. Kiểu tham chiếu rộng hơn không đổi bản chất đối tượng.
9. **Có được dựa vào ConcurrentModificationException để phát hiện mọi lỗi sửa Vector khi đọc Enumeration không?** Không. Enumeration từ Vector không fail-fast; sửa cấu trúc trong tình huống API cảnh báo có thể cho kết quả không được xác định.
10. **Java 8 có gọi Enumeration.asIterator được không?** Không. asIterator có từ Java 9; có thể dùng adapter thủ công khi buộc tương thích Java 8.

## 16. Bài tập áp dụng

### 16.1. Giữ thứ tự và phần tử trùng của phần còn lại

Tạo Vector<Integer> chứa 4,4,8; lấy phần tử đầu bằng nextElement rồi thu phần còn lại bằng Collections.list.

Kết quả cần kiểm tra: phần đã đọc là 4, List kết quả là `[4, 8]`, Vector nguồn vẫn là `[4, 4, 8]`. Đổi phần tử đầu của List kết quả thành 40 chỉ làm List thành `[40, 8]`, không tự sửa Vector nguồn.

Sau đó thu lần nữa từ đúng Enumeration cũ. Kết quả phải rỗng. Giải thích được vì sao một Enumeration mới từ Vector vẫn có thể đọc đầy đủ.

### 16.2. Chọn một đường đọc sau khi thích nghi

Tạo Vector<String> chứa X,Y,Z; đọc X qua Enumeration rồi dùng asIterator. Chỉ dùng Iterator cho phần còn lại.

Kết quả cần kiểm tra: Iterator đọc Y và Z, hasNext sau đó false. Không thêm lời gọi trực tiếp vào Enumeration sau khi tạo adapter. Giải thích vì sao “đang giữ hai biến” không đồng nghĩa “có hai lượt độc lập”.

### 16.3. Chọn chuyển đổi theo yêu cầu của mã gọi

Có một phương thức nhận Enumeration<String> và chỉ cần in từng tên một lần. Một phương thức khác cần xem tên ở chỉ số 0 và duyệt dữ liệu hai lần.

Với phương thức thứ nhất, có thể duyệt trực tiếp hoặc thích nghi Iterator mà không cần thu toàn bộ vào List. Với phương thức thứ hai, thu List một lần từ phần còn lại, kiểm tra rỗng trước khi lấy chỉ số 0, rồi thực hiện các lượt duyệt từ List đó.

Nêu rõ điều kiện nguồn còn đủ dữ liệu mong muốn. Nếu Enumeration đã bị đọc trước, chuyển sang List không khôi phục phần đã mất khỏi lượt đọc.

## 17. Nguồn đối chiếu và phạm vi kiểm chứng

- [Enumeration — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Enumeration.html): hasMoreElements, nextElement, asIterator, mốc Java 9 và ràng buộc sử dụng Enumeration sau khi thích nghi.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): list trả ArrayList, thứ tự thu phần tử, enumeration và emptyEnumeration.
- [Iterator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): các phương thức duyệt, remove tùy chọn, forEachRemaining và giới hạn hành vi liên quan.
- [Vector — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html): nguồn Enumeration trong ví dụ và cảnh báo khi nguồn thay đổi cấu trúc.

Bốn chương trình đầy đủ đã được biên dịch bằng javac với `--release 17` và chạy trên JDK 24.0.2, cho đúng stdout được ghi trong bài. Chương trình adapter thủ công còn được biên dịch thành công với `--release 8`. Các đoạn được ghi là minh họa cần đặt trong ngữ cảnh có sẵn biến và import tương ứng; chúng không được trình bày như tệp chạy độc lập.
