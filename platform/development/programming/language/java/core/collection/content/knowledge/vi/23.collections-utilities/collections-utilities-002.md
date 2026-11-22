# binarySearch và điều kiện danh sách đã được sắp xếp

## 1. Vì sao tìm kiếm nhị phân cần thứ tự?

Giả sử danh sách các mốc đã có thứ tự 3, 7, 11, 15, 19, 23, 27. Muốn tìm 19, ta có thể so với phần tử ở giữa là 15. Vì 19 đứng sau 15 theo thứ tự đang dùng, toàn bộ phần phía trước và chính 15 đều không thể là đáp án. Chỉ cần tiếp tục trong nửa còn lại.

Đó là ý tưởng của **tìm kiếm nhị phân (binary search)**: mỗi lần so sánh loại bỏ một phần lớn vùng còn có thể chứa khóa tìm.

Việc loại bỏ ấy chỉ có căn cứ khi danh sách đã được sắp theo đúng phép so sánh. Nếu 19 có thể nằm tùy ý ở phía trước 15, loại bỏ nửa trước có thể bỏ luôn đáp án.

Một cách chạy minh họa trên danh sách trên:

| Lần | Vùng chỉ số còn xét | Phần tử giữa | So với 19 | Quyết định |
|---|---|---|---|---|
| 1 | 0 đến 6 | 15 tại 3 | 15 đứng trước 19 | Chỉ còn vùng 4 đến 6 |
| 2 | 4 đến 6 | 23 tại 5 | 23 đứng sau 19 | Chỉ còn vùng 4 đến 4 |
| 3 | 4 đến 4 | 19 tại 4 | Bằng nhau theo phép so sánh | Tìm thấy tại 4 |

Bảng giải thích một cách chia vùng hợp lệ, không yêu cầu mọi bản triển khai thư viện phải chọn đúng các bước giữa như vậy.

Collections.binarySearch là tiện ích tìm trên List. Nó **không tự sắp xếp danh sách**, không tìm tuyến tính để cứu đầu vào sai, và không chèn phần tử giúp nơi gọi.

Bài học đi từ điều kiện thứ tự, cách đọc kết quả, comparator, phần tử trùng đến việc duy trì danh sách khi sử dụng thật. Ba chương trình đầy đủ chạy bằng Java 17 trở lên và chỉ dùng thư viện chuẩn.

## 2. “Đã sắp xếp” là theo phép so sánh nào?

### 2.1. Hai dạng gọi chính

| Dạng gọi | Thứ tự danh sách phải có |
|---|---|
| Collections.binarySearch(list,key) | Thứ tự tự nhiên của các phần tử, tăng dần theo Comparable |
| Collections.binarySearch(list,key,order) | Tăng dần theo quan hệ do order định nghĩa |
| Collections.binarySearch(list,key,null) | Dùng thứ tự tự nhiên như trường hợp không truyền comparator |

“Thứ tự tự nhiên” là thứ tự do kiểu phần tử định nghĩa, chẳng hạn Integer theo giá trị số, String theo thứ tự so sánh chuỗi của String. Một dãy trông tăng theo cách người dùng đọc chưa chắc tăng theo compareTo của kiểu dữ liệu.

Ví dụ các String "1","10","2" có thể ở đúng thứ tự tự nhiên dù không giống thứ tự số 1,2,10. Nếu nghiệp vụ muốn so như số, phải chuyển thành kiểu số hoặc cung cấp phép so sánh thích hợp rồi sắp theo nó.

List không tự mang một Comparator cho binarySearch lấy lại như TreeSet/TreeMap. Mỗi lần gọi dạng có Comparator phải truyền quy tắc đúng với dữ liệu đang tìm.

### 2.2. Không giảm, không phải tăng nghiêm ngặt

Với comparator c hợp lệ và ổn định, danh sách đã sắp khi mọi cặp kề nhau thỏa:

c.compare(list.get(i), list.get(i + 1)) <= 0.

Phần tử trùng hoặc bằng nhau theo comparator được phép. Dãy 1,2,2,2,4 vẫn đã sắp. Không cần loại bỏ phần tử trùng trước khi dùng binarySearch.

Danh sách rỗng và một phần tử không có cặp kề vi phạm thứ tự. Điều kiện so sánh với khóa tìm vẫn phải được sử dụng đúng; không dùng một trường hợp rỗng để suy rằng mọi kiểu khóa đều tương thích ở các trường hợp khác.

### 2.3. Giảm dần theo số vẫn là tăng theo comparator đảo

Comparator.reverseOrder() cho số nguyên đặt 50 trước 40, 40 trước 30. Danh sách 50,40,30,20,10 vì thế đã sắp tăng theo quan hệ của comparator đó.

Tìm trên danh sách này bằng dạng mặc định dùng thứ tự tự nhiên là sai điều kiện. Cần truyền Comparator giảm dần tương ứng.

Cách viết dễ kiểm soát là giữ comparator trong một biến và dùng nó cho cả sort lẫn binarySearch. Không bắt buộc là cùng một đối tượng Comparator theo ==; điều cần đúng là danh sách vẫn có thứ tự theo quan hệ dùng để tìm.

Một thứ tự chi tiết hơn đôi khi vẫn tương thích với tìm theo tiêu chí thô hơn. Chẳng hạn sắp theo điểm rồi tên vẫn giữ thứ tự theo điểm. Nhưng sắp chỉ theo điểm không tự bảo đảm các phần tử cùng điểm đã tăng theo tên để tìm bằng comparator điểm rồi tên. Cần kiểm tra quan hệ thực tế, không dựa vào hai tên comparator có vẻ gần nhau.

Đặc tả của [Collections.binarySearch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)) yêu cầu danh sách được sắp trước theo phép so sánh dùng cho lời gọi.

### 2.4. Vi phạm điều kiện không bảo đảm nhận một ngoại lệ

Nếu danh sách chưa được sắp đúng, hợp đồng không bảo đảm kết quả tìm kiếm. Có lần tìm thấy, có lần trả số âm dù phần tử có thật, hoặc cho vị trí chèn không có ý nghĩa đúng với toàn danh sách.

Không viết code bắt một ngoại lệ “danh sách chưa sắp” rồi mới sửa. binarySearch không có trách nhiệm duyệt toàn bộ danh sách để phát hiện điều kiện đó trước mỗi lần tìm.

## 3. Kết quả trả về có hai nhánh, không chỉ có chỉ số hoặc -1

Gọi r = Collections.binarySearch(list,key).

### 3.1. r >= 0: tìm thấy một phần tử so sánh bằng khóa

r là chỉ số bắt đầu từ 0 trong chính list được truyền vào. Có thể lấy list.get(r) khi danh sách chưa thay đổi làm vô hiệu ý nghĩa vị trí.

Chỉ số 0 là tìm thấy ở phần tử đầu, không phải thất bại. Vì vậy điều kiện đúng để kiểm tra có kết quả là r >= 0, không phải r > 0.

“Tìm thấy” được hiểu theo compareTo/Comparator bằng 0. Nó không mặc định nghĩa là tìm thấy cùng một tham chiếu hoặc một đối tượng equals khóa; ví dụ đối tượng có comparator theo một trường sẽ minh họa sự khác nhau này.

### 3.2. r < 0: mã hóa vị trí chèn

Khi không tìm thấy, r không chỉ là một mã thất bại chung. Nó có dạng:

r = -insertionPoint - 1.

insertionPoint là vị trí mà khóa có thể được chèn vào để giữ thứ tự: vị trí phần tử đầu tiên đứng sau khóa theo phép so sánh, hoặc list.size() nếu khóa đứng sau toàn bộ phần tử.

Vì đang ở nhánh **không có phần tử so sánh bằng khóa**, vị trí đầu tiên không nhỏ hơn khóa và vị trí đầu tiên lớn hơn khóa trùng nhau.

Giải mã bằng:

insertionPoint = -(r + 1).

Vị trí chèn thuộc [0,size], trong khi chỉ số phần tử hợp lệ thuộc [0,size). Giá trị size hợp lệ cho add(size,key) của một list có hỗ trợ thêm, nhưng không hợp lệ cho get(size).

### 3.3. Ví dụ giải mã

Nguồn có thứ tự [-10,0,10,20,30]:

| Khóa | Kết quả r | Ý nghĩa |
|---|---|---|
| -10 | 0 | Tìm thấy phần tử đầu |
| 10 | 2 | Tìm thấy tại chỉ số 2 |
| 15 | -4 | Không có; chèn tại 3 trước 20 |
| -20 | -1 | Không có; chèn tại 0 |
| 40 | -6 | Không có; chèn tại 5, tức cuối list |

Với list rỗng, vị trí chèn là 0 nên kết quả là -1. -1 không có nghĩa duy nhất là “không tìm thấy ở bất cứ đâu” mà còn mã hóa chính vị trí 0.

Không dùng Math.abs(r) để lấy vị trí chèn. Với r = -4, Math.abs cho 4 trong khi vị trí đúng là 3. Cách -(r + 1) cũng tránh phải xử lý một bước lấy đối của số âm nhỏ nhất trước khi trừ 1.

## 4. Chương trình đọc kết quả, chèn khi chưa có và xử lý phần tử trùng

Tệp **BinarySearchResultDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class BinarySearchResultDemo {
    private static void report(List<Integer> values, int key) {
        int result = Collections.binarySearch(values, key);
        if (result >= 0) {
            System.out.println("key=" + key + ", found=" + result +
                    ", value=" + values.get(result));
        } else {
            int insertionPoint = -(result + 1);
            System.out.println("key=" + key + ", result=" + result +
                    ", insertion=" + insertionPoint);
        }
    }

    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(List.of(-10, 0, 10, 20, 30));
        report(values, -10);
        report(values, 10);
        report(values, 15);
        report(values, -20);
        report(values, 40);
        report(List.of(), 42);

        int result = Collections.binarySearch(values, 15);
        if (result < 0) {
            values.add(-(result + 1), 15);
        }
        System.out.println("afterInsert=" + values);
        System.out.println("readOnlySearch=" +
                Collections.binarySearch(List.of(2, 4, 6, 8), 6));

        List<Integer> duplicates = List.of(-2, 0, 0, 0, 4);
        int duplicateResult = Collections.binarySearch(duplicates, 0);
        System.out.println("duplicateFound=" + (duplicateResult >= 0));
        System.out.println("duplicateMatched=" + duplicates.get(duplicateResult));
        System.out.println("duplicateIndexInRange=" +
                (duplicateResult >= 1 && duplicateResult <= 3));
        report(duplicates, 1);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BinarySearchResultDemo.java
java BinarySearchResultDemo
```

Stdout chính xác:

```text
key=-10, found=0, value=-10
key=10, found=2, value=10
key=15, result=-4, insertion=3
key=-20, result=-1, insertion=0
key=40, result=-6, insertion=5
key=42, result=-1, insertion=0
afterInsert=[-10, 0, 10, 15, 20, 30]
readOnlySearch=2
duplicateFound=true
duplicateMatched=0
duplicateIndexInRange=true
key=1, result=-5, insertion=4
```

### 4.1. Tìm kiếm không cần list sửa được

readOnlySearch tìm trên List.of(2,4,6,8) và trả 2. binarySearch chỉ đọc; nó không cần add/set hay tự gọi sort.

Ngược lại, đoạn chèn 15 cần list hỗ trợ add(index,value). Chỉ số chèn đúng không làm một list không sửa được bỗng hỗ trợ thao tác thêm.

Nếu phải sắp một list không cho sửa mà vẫn muốn giữ dữ liệu đầu vào, có thể tạo ArrayList riêng rồi sắp bản riêng. Không gọi sort lên kết quả chỉ đọc và cho rằng binarySearch sẽ làm phần còn lại.

### 4.2. Số âm phải được xử lý trước khi truy cập

report() chỉ gọi get(result) ở nhánh result >= 0. Ở nhánh âm, nó giải mã vị trí chèn và in thông tin.

Nếu dùng số âm thẳng làm chỉ số, đó là lỗi của nơi gọi, thường dẫn tới IndexOutOfBoundsException. binarySearch đã trả thông tin hợp lệ về việc không có khóa.

### 4.3. Khi trùng, không cam kết phần tử đầu hoặc cuối

duplicates có các phần tử bằng 0 ở chỉ số 1,2,3. Chương trình kiểm tra kết quả nằm trong khoảng đó và phần tử tại kết quả bằng 0, nhưng không in một chỉ số cụ thể rồi coi đó là hợp đồng.

Collections.binarySearch không cam kết trả vị trí đầu tiên hoặc cuối cùng khi có nhiều phần tử so sánh bằng khóa. Sort ổn định cũng không thay đổi hợp đồng này: giữ thứ tự của các phần tử bằng nhau khi sắp không có nghĩa thuật toán tìm phải chọn phần tử đầu trong nhóm.

Nếu chỉ cần biết có ít nhất một phần tử bằng khóa, kết quả bất kỳ trong nhóm là đủ. Nếu cần đếm, lấy toàn bộ nhóm hoặc chèn trước/sau nhóm, cần tìm biên riêng.

## 5. Comparator quyết định nghĩa của tìm thấy và vị trí chèn

Chương trình sau có các Score gồm tên và điểm. Comparator đầu tiên chỉ nhìn points, nên hai Score khác tên có thể so sánh bằng 0 dù record.equals() trả false.

Nó cũng dùng một danh sách số giảm dần và một comparator cho phép null để kiểm tra điều kiện thứ tự ở các trường hợp khác nhau.

Tệp **BinarySearchComparatorDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class BinarySearchComparatorDemo {
    record Score(String name, int points) {}

    public static void main(String[] args) {
        Comparator<Score> byPoints = Comparator.comparingInt(Score::points);
        List<Score> scores = new ArrayList<>(List.of(
                new Score("A", 30), new Score("B", 10),
                new Score("C", 20), new Score("D", 20)));
        scores.sort(byPoints);
        System.out.println("sortedPoints=" +
                scores.stream().map(Score::points).toList());

        Score probe = new Score("probe", 20);
        int result = Collections.binarySearch(scores, probe, byPoints);
        Score matched = scores.get(result);
        System.out.println("matchedPoints=" + matched.points());
        System.out.println("compareZero=" + (byPoints.compare(matched, probe) == 0));
        System.out.println("equalsProbe=" + matched.equals(probe));
        System.out.println("indexOfProbe=" + scores.indexOf(probe));

        int missing = Collections.binarySearch(
                scores, new Score("probe", 25), byPoints);
        System.out.println("missing25=" + missing);
        System.out.println("insert25At=" + (-(missing + 1)));

        Comparator<Score> byPointsThenName =
                byPoints.thenComparing(Score::name);
        scores.sort(byPointsThenName);
        int exact = Collections.binarySearch(
                scores, new Score("D", 20), byPointsThenName);
        System.out.println("exactName=" + scores.get(exact).name());

        Comparator<Integer> descending = Comparator.reverseOrder();
        List<Integer> descendingValues =
                new ArrayList<>(List.of(50, 40, 30, 20, 10));
        int reverseMissing =
                Collections.binarySearch(descendingValues, 35, descending);
        int reverseInsertion = -(reverseMissing + 1);
        System.out.println("descendingMissing35=" + reverseMissing);
        System.out.println("descendingInsertion=" + reverseInsertion);
        descendingValues.add(reverseInsertion, 35);
        System.out.println("descendingAfterInsert=" + descendingValues);

        Comparator<Integer> nullsFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        List<Integer> nullable = Arrays.asList(null, 10, 20);
        System.out.println("nullKeyIndex=" +
                Collections.binarySearch(nullable, null, nullsFirst));
        System.out.println("nullableMissing15=" +
                Collections.binarySearch(nullable, 15, nullsFirst));
        System.out.println("nullComparatorUsesNatural=" +
                Collections.binarySearch(List.of(1, 2, 3), 2, null));
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 BinarySearchComparatorDemo.java
java BinarySearchComparatorDemo
```

Stdout chính xác:

```text
sortedPoints=[10, 20, 20, 30]
matchedPoints=20
compareZero=true
equalsProbe=false
indexOfProbe=-1
missing25=-4
insert25At=3
exactName=D
descendingMissing35=-3
descendingInsertion=2
descendingAfterInsert=[50, 40, 35, 30, 20, 10]
nullKeyIndex=0
nullableMissing15=-3
nullComparatorUsesNatural=1
```

### 5.1. Tìm theo điểm khác tìm đúng toàn bộ record

probe có tên probe và điểm 20. Sau khi sắp theo points, binarySearch trả một Score có điểm 20. Tên có thể là C hoặc D; chương trình không dựa vào lựa chọn nào.

byPoints.compare(matched,probe) bằng 0 nhưng matched.equals(probe) bằng false, vì record.equals xét các thành phần của record. scores.indexOf(probe) trả -1 do dùng quan hệ equals.

Đây là hai câu hỏi khác nhau:

- binarySearch với byPoints: có phần tử nào thuộc nhóm điểm 20 không?
- indexOf với probe: có phần tử equals đúng probe theo hợp đồng lớp không?

Comparator chỉ theo points vẫn là một phép so sánh hợp lệ cho nhu cầu tìm nhóm điểm. Không bắt buộc mọi comparator dùng tìm trong List phải phân biệt mọi trường của record.

Muốn tìm theo điểm rồi tên, chương trình sắp lại bằng byPoints.thenComparing(Score::name) và tìm với chính quan hệ đó. Kết quả exactName là D.

### 5.2. Vị trí chèn cũng dùng chiều của comparator

Trong danh sách 50,40,30,20,10 theo reverseOrder, 35 được chèn tại 2, giữa 40 và 30. Mã trả về là -3.

Không giải mã xong rồi áp một quy tắc vị trí theo số tăng dần. Vị trí chèn đã là vị trí trong dãy giảm dần được truyền vào.

### 5.3. Comparator null và khóa null là hai chuyện khác nhau

Truyền null ở tham số comparator có nghĩa dùng thứ tự tự nhiên; nó không phải một comparator cho phép phần tử hoặc khóa null.

Comparator.nullsFirst(naturalOrder()) mới biểu đạt chính sách đặt null trước các số. Danh sách nullable trong ví dụ đã đúng thứ tự của chính comparator đó, nên tìm null tại 0 hợp lệ và tìm 15 trả vị trí chèn 2.

Không mặc định natural ordering biết so sánh null. Một trường hợp đặc biệt chưa cần so sánh, chẳng hạn list rỗng, cũng không chứng minh null được hỗ trợ chung cho mọi dữ liệu.

### 5.4. Phép so sánh phải đúng và ổn định

Không viết comparator cho số nguyên bằng a - b nếu miền giá trị có thể làm phép trừ tràn số. Dùng Integer.compare hoặc các factory comparingInt như ví dụ giúp biểu đạt phép so sánh đúng hơn.

Comparator cần thỏa hợp đồng thứ tự, gồm tính nhất quán và bắc cầu. Nó cũng không nên thay đổi ý nghĩa giữa sort và search vì một cờ cấu hình hoặc trạng thái bên ngoài bị đổi.

Tài liệu [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) giải thích quan hệ so sánh và việc compare bằng 0 có thể khác equals. [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) quy định nền tảng cho trường hợp thứ tự tự nhiên.

## 6. Muốn phần tử đầu, cuối hoặc toàn bộ nhóm trùng thì tìm biên

### 6.1. Hai biên cần phân biệt

Trên list đã sắp theo comparator c:

- lowerBound(key): vị trí đầu tiên có phần tử không đứng trước key, tức c.compare(element,key) >= 0; nếu không có thì trả size.
- upperBound(key): vị trí đầu tiên có phần tử đứng sau key, tức c.compare(element,key) > 0; nếu không có thì trả size.

Các phần tử so sánh bằng key nằm trong khoảng chỉ số [lowerBound,upperBound). Số phần tử trong nhóm là upperBound - lowerBound.

Nếu hai biên bằng nhau, không có phần tử so sánh bằng khóa. Vị trí đó chính là vị trí chèn khi không tìm thấy.

Nếu nhóm không rỗng:

- Vị trí đầu nhóm là lowerBound.
- Vị trí cuối nhóm là upperBound - 1.
- Chèn ở lowerBound đặt phần tử mới trước nhóm.
- Chèn ở upperBound đặt phần tử mới sau nhóm.

Đây là các hàm tự viết của ví dụ, không phải tên phương thức có sẵn trong Collections. Chúng vẫn yêu cầu list đã được sắp và comparator đúng.

### 6.2. Chương trình biên, kiểm tra thứ tự và chỉ số của subList

Tệp **BinarySearchBoundsDemo.java**:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class BinarySearchBoundsDemo {
    public static <T> int lowerBound(
            List<? extends T> values, T key, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        int low = 0;
        int high = values.size();
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (order.compare(values.get(mid), key) < 0) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        return low;
    }

    public static <T> int upperBound(
            List<? extends T> values, T key, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        int low = 0;
        int high = values.size();
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (order.compare(values.get(mid), key) <= 0) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        return low;
    }

    public static <T> boolean isSorted(
            List<? extends T> values, Comparator<? super T> order) {
        Objects.requireNonNull(values);
        Objects.requireNonNull(order);
        Iterator<? extends T> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return true;
        }
        T previous = iterator.next();
        while (iterator.hasNext()) {
            T current = iterator.next();
            if (order.compare(previous, current) > 0) {
                return false;
            }
            previous = current;
        }
        return true;
    }

    public static void main(String[] args) {
        Comparator<Integer> ascending = Comparator.naturalOrder();
        List<Integer> values = List.of(1, 2, 2, 2, 4);
        int lower = lowerBound(values, 2, ascending);
        int upper = upperBound(values, 2, ascending);
        System.out.println("bounds2=" + lower + "," + upper);
        System.out.println("count2=" + (upper - lower));
        System.out.println("equalRange=" + values.subList(lower, upper));
        System.out.println("bounds3=" +
                lowerBound(values, 3, ascending) + "," +
                upperBound(values, 3, ascending));
        System.out.println("beforeAll=" + lowerBound(values, 0, ascending));
        System.out.println("afterAll=" + upperBound(values, 9, ascending));
        System.out.println("emptyBounds=" +
                lowerBound(List.<Integer>of(), 2, ascending) + "," +
                upperBound(List.<Integer>of(), 2, ascending));
        System.out.println("sorted=" + isSorted(values, ascending));
        System.out.println("unsorted=" +
                isSorted(List.of(1, 3, 2), ascending));

        List<Integer> descending = List.of(5, 4, 4, 2);
        Comparator<Integer> reverse = Comparator.reverseOrder();
        System.out.println("descendingBounds4=" +
                lowerBound(descending, 4, reverse) + "," +
                upperBound(descending, 4, reverse));

        List<Integer> whole = List.of(0, 10, 20, 30, 40);
        int from = 1;
        List<Integer> part = whole.subList(from, 4);
        int localFound = Collections.binarySearch(part, 20);
        int localMissing = Collections.binarySearch(part, 25);
        System.out.println("localFound=" + localFound);
        System.out.println("wholeFound=" + (from + localFound));
        System.out.println("localMissing=" + localMissing);
        System.out.println("wholeInsertion=" + (from - (localMissing + 1)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BinarySearchBoundsDemo.java
java BinarySearchBoundsDemo
```

Stdout chính xác:

```text
bounds2=1,4
count2=3
equalRange=[2, 2, 2]
bounds3=4,4
beforeAll=0
afterAll=5
emptyBounds=0,0
sorted=true
unsorted=false
descendingBounds4=1,3
localFound=1
wholeFound=2
localMissing=-3
wholeInsertion=3
```

### 6.3. Tại sao thay một dấu so sánh làm đổi biên?

Trong lowerBound, khi phần tử giữa đứng trước key, biên cần tìm phải nằm bên phải nên low = mid + 1. Khi phần tử giữa bằng hoặc đứng sau key, chưa được bỏ qua vị trí giữa, nên high = mid.

Trong upperBound, trường hợp bằng key cũng phải đi sang phải. Vì vậy điều kiện ở nhánh cập nhật low dùng <= 0 thay vì < 0.

Vùng tìm được biểu diễn bằng [low,high), cho phép kết quả là size mà không truy cập get(size). Khi low == high, vòng lặp kết thúc tại đúng biên.

Cách tính mid = low + (high - low) / 2 tránh cộng trực tiếp hai chỉ số lớn trước khi chia. Mỗi lần lặp đều làm vùng còn lại nhỏ hơn.

Trên [1,2,2,2,4], biên của 2 là 1 và 4, nên nhóm có ba phần tử. Biên của 3 đều là 4, xác nhận không có 3 và có thể chèn tại 4.

### 6.4. Những hàm minh họa không có mọi chính sách của thư viện

Hai hàm biên trong chương trình yêu cầu Comparator không null một cách tường minh. Muốn thứ tự tự nhiên, truyền Comparator.naturalOrder(). Đây là hợp đồng của hàm tự viết, khác dạng Collections.binarySearch(...,null) dùng thứ tự tự nhiên.

Cả hai dùng get(mid), nên phù hợp nhất với list truy cập ngẫu nhiên nhanh. Chúng có thể tính đúng trên list truy cập tuần tự hợp lệ, nhưng không tự có tối ưu duyệt iterator của Collections.binarySearch cho list lớn kiểu đó.

isSorted dùng iterator để kiểm tra các cặp kề nhau. Khi comparator là một quan hệ thứ tự đúng và ổn định, điều kiện không giảm giữa các cặp kề xác nhận danh sách đã sắp theo quan hệ đó. Hàm không kiểm chứng toàn bộ hợp đồng bắc cầu hay tính đúng của một Comparator tùy ý.

## 7. Tìm trên subList: kết quả thuộc hệ chỉ số của đối tượng được truyền vào

Trong chương trình, whole là [0,10,20,30,40]. part = whole.subList(1,4) chứa [10,20,30].

Tìm 20 trên part trả chỉ số 1. Chỉ số tương ứng trong whole là 1 + 1 = 2. binarySearch không tự trả chỉ số của list cha.

Khi không có 25 trong part:

- Kết quả localMissing là -3.
- Vị trí chèn trong part là -(-3 + 1) = 2.
- Vị trí chèn tương ứng trong whole là from + 2 = 3.

Phải **giải mã số âm trước**, rồi mới chuyển hệ tọa độ. Không cộng offset thẳng vào một kết quả âm đã mã hóa rồi coi đó là chỉ số hoặc kết quả đã mã hóa của list cha.

Nếu có kết quả r >= 0, chuyển chỉ số bằng from + r. Nếu r < 0, chuyển vị trí chèn bằng from - (r + 1).

Quy tắc này áp dụng khi quan hệ giữa subList và list cha vẫn hợp lệ và chưa có thay đổi làm vô hiệu view/chỉ số. List.subList có điều kiện riêng về sửa cấu trúc ở nguồn; lớp bọc chỉ đọc hoặc binarySearch không loại bỏ các điều kiện ấy.

Các phần tử của một đoạn liên tiếp trong list đã sắp vẫn giữ thứ tự theo cùng comparator. Tuy nhiên, điều đó không cho phép dùng một comparator khác hoặc bỏ qua việc list cha thay đổi.

## 8. Giữ điều kiện sắp xếp trong suốt vòng đời dữ liệu

### 8.1. Một lần sort trong quá khứ chưa đủ

Sau sort, các thao tác sau có thể làm danh sách không còn thứ tự phù hợp:

- Thêm một phần tử vào vị trí tùy ý không đúng thứ tự.
- Dùng set thay phần tử bằng một giá trị phá quan hệ với phần tử kề.
- Đảo hoặc trộn thứ tự danh sách rồi vẫn tìm bằng comparator cũ.
- Đổi thuộc tính được comparator đọc trên một đối tượng phần tử.
- Đổi quy tắc của comparator hoặc trạng thái bên ngoài mà nó dựa vào.

Không phải mọi sửa đổi đều phá thứ tự. Xóa phần tử khỏi một list đã sắp vẫn giữ thứ tự của các phần tử còn lại. Chèn đúng vị trí tính được hoặc thay bằng giá trị vẫn nằm giữa hai hàng xóm có thể giữ điều kiện.

Điều cần theo dõi là quan hệ thứ tự hiện tại, không chỉ một cờ “đã từng gọi sort”.

### 8.2. Chèn khi chưa có và chèn thêm vào nhóm đã có

Ở nhánh r < 0, vị trí chèn giải mã được bảo toàn thứ tự khi chèn đúng khóa vừa tìm vào một list chưa thay đổi.

Ở nhánh r >= 0, nếu mục đích là bảo đảm duy nhất theo comparator thì có thể không chèn. Nếu muốn giữ nhiều phần tử bằng nhau, phải xác định vị trí trong nhóm có quan trọng không.

Chèn tại một vị trí khớp có thể vẫn giữ thứ tự theo comparator, nhưng không bảo đảm đặt sau toàn bộ các phần tử cùng khóa. Muốn trước hoặc sau nhóm, dùng biên tương ứng.

Nếu đối tượng có thêm tiêu chí phụ, cần thống nhất comparator để quyết định điều kiện thứ tự đầy đủ. Không tìm vị trí chỉ theo điểm rồi mặc định danh sách vẫn đúng thứ tự điểm-và-tên sau khi chèn tên bất kỳ.

### 8.3. Trường của phần tử mutable cũng là một đường làm hỏng thứ tự

Giữ list không cho add/set không làm các phần tử bên trong bất biến. Nếu một Score dạng mutable được tăng điểm trực tiếp, vị trí vật lý cũ có thể không còn phù hợp với điểm mới.

Khi đó binarySearch vẫn nhìn thứ tự vật lý đang có, không tự sắp lại vì đối tượng đổi thuộc tính. Có thể cần cập nhật qua một lớp quản lý, đưa phần tử ra rồi chèn lại đúng vị trí, sắp lại khi kết thúc lô cập nhật hoặc dùng dữ liệu bất biến theo yêu cầu.

Một bản sao cấu trúc bằng new ArrayList<>(source) cũng có thể vẫn giữ cùng các đối tượng mutable, nên không tự giải quyết vấn đề này.

### 8.4. Kết quả chỉ số không phải định danh ổn định của đối tượng

Sau khi chèn/xóa phần tử trước vị trí vừa tìm, cùng một đối tượng có thể chuyển sang chỉ số khác. Lưu r rồi dùng lại sau nhiều cập nhật có thể lấy nhầm phần tử.

Nếu cần giữ một thực thể, hãy giữ thông tin nhận diện hoặc tham chiếu phù hợp với vòng đời dữ liệu; nếu cần một vị trí cho thao tác hiện tại, phải kiểm soát việc danh sách không đổi giữa tìm và sử dụng.

Trong môi trường nhiều luồng, chuỗi tìm → giải mã → chèn hoặc tìm → get có thể cần thực hiện trong cùng cơ chế đồng bộ/quyền sở hữu. binarySearch không tự khóa toàn bộ quy trình ấy.

## 9. Chi phí: ít phép so sánh chưa chắc ít bước truy cập

### 9.1. Trên list truy cập ngẫu nhiên

Nếu get(index) có chi phí gần như hằng số và phép so sánh có chi phí được kiểm soát, tìm kiếm nhị phân cần O(log n) lần thu hẹp vùng.

ArrayList là ví dụ thường gặp cho truy cập vị trí nhanh. Khi comparator so sánh những đối tượng lớn hoặc phải tính toán nhiều, chi phí mỗi phép so sánh vẫn cần tính thêm. O(log n) không có nghĩa mọi phép so sánh đều miễn phí.

### 9.2. Trên LinkedList hoặc list truy cập tuần tự lớn

LinkedList phải đi qua các liên kết để đến một chỉ số. Nếu tự viết thuật toán dùng get(mid) lặp lại mà bỏ qua kiểu list, tổng chi phí có thể xấu hơn điều người viết suy từ số lần so sánh.

Đặc tả Collections.binarySearch mô tả việc dùng cách tìm dựa trên iterator cho list lớn không triển khai RandomAccess: có O(log n) phép so sánh phần tử nhưng O(n) bước đi qua liên kết. Không được gọi toàn bộ thời gian trên LinkedList là O(log n) chỉ vì thuật toán mang tên binary search.

[RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) là interface đánh dấu để các thuật toán chung phân biệt khả năng truy cập theo vị trí. [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) nêu cách duyệt để tới chỉ số; các bảo đảm thao tác của [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) khác với mô hình đó.

Không hard-code ngưỡng kích thước chuyển thuật toán của một bản JDK vào logic ứng dụng. Ngưỡng và cách triển khai cụ thể không phải điều kiện nghiệp vụ.

### 9.3. Tìm vị trí nhanh không làm chèn ArrayList nhanh như vậy

Ngay cả khi tìm vị trí chèn trên ArrayList có số bước logarithm, chèn giữa list vẫn có thể cần dịch nhiều phần tử, với chi phí tuyến tính theo số phần tử phải dời.

Nếu liên tục thêm dữ liệu và cần thứ tự duy trì sau mỗi lần, hãy đánh giá cả tìm, chèn, xóa và nhu cầu giữ phần tử trùng. Một cấu trúc có thứ tự khác có thể phù hợp hơn, nhưng không thay List bằng Set/Map mà bỏ qua khác biệt về vị trí và quan hệ bằng nhau.

### 9.4. Có nên sort trước mọi lần tìm?

Nếu dữ liệu chưa được sắp và chỉ cần một lần tìm theo equals, tìm tuyến tính có thể đơn giản và phù hợp hơn việc sort toàn bộ. Sắp xếp còn làm đổi thứ tự đầu vào nếu thực hiện trực tiếp.

Với nhiều truy vấn trên dữ liệu ít thay đổi, sắp một lần rồi tìm nhiều lần có thể có lợi. Trong phân tích sắp xếp bằng so sánh thông thường, chi phí chuẩn bị cỡ O(n log n) có thể được phân bổ cho nhiều lần tìm O(log n) trên cấu trúc truy cập ngẫu nhiên.

Nếu cần giữ thứ tự nguồn ban đầu, tạo bản riêng để sắp hoặc giữ thêm chỉ số gốc trong mô hình. Kết quả binarySearch trên bản đã sắp là chỉ số của bản đó, không phải chỉ số cũ của đầu vào chưa sắp.

## 10. Phát hiện sai điều kiện và xử lý đầu vào

### 10.1. Kiểm tra thứ tự khi nào?

Hàm isSorted trong BinarySearchBoundsDemo kiểm tra bằng cách đi qua từng cặp kề, có chi phí O(n). Nó hữu ích ở biên nhận dữ liệu, lúc gỡ lỗi hoặc khi viết kiểm thử.

Nếu kiểm tra toàn bộ list trước mọi lần binarySearch, tổng chi phí mỗi lần không còn chỉ O(log n). Trong một lớp quản lý dữ liệu, thường nên bảo đảm thứ tự bằng thiết kế của các đường cập nhật, hoặc kiểm tra khi dữ liệu đi vào/thay đổi theo lô.

Không dùng isSorted như bằng chứng rằng một Comparator vi phạm hợp đồng bỗng trở nên đúng. Hàm kiểm tra thứ tự của dữ liệu theo comparator được cung cấp, trong giả định comparator là quan hệ thích hợp.

### 10.2. Lỗi kiểu và khả năng so sánh

Dạng tìm tự nhiên cần các phần tử và khóa so sánh được với nhau theo Comparable. Generics giúp phát hiện nhiều lỗi lúc biên dịch; nếu bỏ qua bằng raw type hoặc ép kiểu không đúng, vẫn có thể gặp ClassCastException lúc chạy.

Dạng có Comparator không bắt buộc lớp phần tử tự triển khai Comparable, như record Score trong ví dụ. Tuy vậy, comparator phải xử lý được các phần tử thực tế và khóa tìm.

Truyền list null không có dữ liệu để tìm và không hợp lệ. Khóa null/phần tử null cần một chính sách so sánh hỗ trợ chúng; việc list triển khai nào đó cho phép chứa null không đủ để kết luận phép tìm theo thứ tự tự nhiên hợp lệ.

### 10.3. Dữ liệu sai thứ tự không nên có “stdout chuẩn” cho kết quả tìm

Một ví dụ có chủ đích dùng danh sách chưa sắp rồi in một chỉ số từ binarySearch chỉ cho thấy hành vi quan sát được của lần chạy ấy. Nó không tạo hợp đồng về kết quả trên đầu vào vi phạm điều kiện.

Trong bài này, isSorted([1,3,2]) trả false để phát hiện vấn đề. Không dùng kết quả tìm trên dãy ấy làm bài tập yêu cầu nhớ một con số cố định.

## 11. Quy trình áp dụng trong một chức năng thực tế

Với một danh sách dữ liệu cần tìm nhiều lần, có thể tổ chức như sau:

1. Xác định chính xác khóa tìm và quan hệ so sánh, gồm tiêu chí phụ nếu cần.
2. Kiểm tra dữ liệu về kiểu, null và các bất biến nghiệp vụ.
3. Tạo hoặc chọn list phù hợp, rồi sắp theo quan hệ đó.
4. Thực hiện các lần binarySearch bằng cùng quan hệ tương thích.
5. Phân nhánh kết quả: chỉ số khớp hoặc vị trí chèn đã giải mã.
6. Nếu cần toàn bộ nhóm bằng nhau, dùng phép tìm biên với hợp đồng rõ.
7. Chỉ cho cập nhật qua các đường giữ được thứ tự hoặc sắp lại khi cần.
8. Kiểm soát việc dữ liệu không đổi giữa tìm và thao tác phụ thuộc chỉ số.

Nếu chỉ cần tìm có/không mà không cần vị trí hoặc thứ tự, một cấu trúc tra cứu theo khóa có thể biểu đạt tốt hơn. Nhưng phải xét quan hệ so sánh: tìm theo Comparator bằng 0 có thể không giống tra cứu theo equals/hashCode.

Nếu truy vấn là “tìm theo điểm”, kết quả so sánh bằng 0 chỉ xác nhận điểm khớp, không chứng minh mọi trường khác trùng khớp. Nếu truy vấn là “tìm đúng thực thể có mã cụ thể”, hãy đưa điều kiện đó vào mô hình chỉ mục hoặc bước kiểm tra phù hợp.

Không dùng binarySearch như một cách tìm phần tử bất kỳ trên mọi List. Nó có giá trị khi ứng dụng thực sự giữ được quan hệ thứ tự cần thiết.

## 12. Những lỗi phổ biến và cách đọc đúng

| Cách dùng sai | Vấn đề | Cách sửa |
|---|---|---|
| Tìm trên list chưa sắp | Việc loại nửa vùng không có căn cứ | Sắp trước hoặc chọn cách tìm khác |
| Sắp theo một quan hệ, tìm bằng quan hệ không tương thích | Điều kiện đã sắp của phép tìm bị vi phạm | Dùng comparator đúng với thứ tự hiện tại |
| Kiểm tra r > 0 | Bỏ sót kết quả tại chỉ số 0 | Kiểm tra r >= 0 |
| Chỉ so r == -1 để xác định không có | Các số âm khác cũng là không có | Phân nhánh r < 0 |
| Dùng Math.abs(r) làm vị trí chèn | Sai công thức và có vấn đề biên số nguyên | Dùng -(r + 1) khi r < 0 |
| Dùng vị trí chèn size cho get | size là biên sau phần tử cuối | Chỉ dùng cho thao tác có hợp đồng nhận biên đó |
| Mặc định kết quả là phần tử đầu nhóm trùng | API không cam kết lựa chọn ấy | Tìm lowerBound/upperBound khi cần |
| Mặc định compare bằng 0 là equals | Có thể chỉ khớp theo một thuộc tính | Hiểu đúng comparator và điều kiện nghiệp vụ |
| Cộng offset vào kết quả âm của subList | Cộng vào dữ liệu đang mã hóa | Giải mã rồi chuyển chỉ số |
| Gọi sort hoặc add trên list chỉ đọc | Tìm đọc được nhưng sửa không được | Chuẩn bị list mutable riêng khi cần |
| Giữ chỉ số qua nhiều cập nhật | Chỉ số có thể trỏ phần tử khác | Dùng trong phạm vi dữ liệu ổn định |
| Gọi mọi binarySearch là O(log n) thời gian | Bỏ qua truy cập LinkedList và chi phí so sánh | Phân tích cả số so sánh lẫn truy cập |

## 13. Bài tập và lời giải

### Bài 1 — Chỉ số 0

List đã sắp [2,5,9]. Tìm 2 trả 0. Điều kiện if (r > 0) có đúng để kiểm tra tìm thấy không?

**Lời giải:** không. 0 là chỉ số hợp lệ của phần tử đầu. Dùng r >= 0; mọi r âm mới thuộc nhánh không tìm thấy.

### Bài 2 — Giải mã vị trí chèn

List [2,5,9], tìm 7. Kết quả là bao nhiêu, và chèn vào đâu?

**Lời giải:** vị trí chèn là 2, trước 9, nên kết quả là -3. Giải mã bằng -(-3 + 1) = 2. Không dùng giá trị tuyệt đối vì nó cho 3.

### Bài 3 — Biên đầu, cuối và list rỗng

Với [2,5,9], tìm 1 và 12 trả gì? Với list rỗng, tìm một số bất kỳ trả gì?

**Lời giải:** tìm 1 có vị trí chèn 0 nên trả -1. Tìm 12 có vị trí chèn 3 nên trả -4. List rỗng có vị trí chèn 0 nên trả -1.

### Bài 4 — Dãy giảm dần

List [9,7,4] được sắp theo reverseOrder. Tìm 8 bằng comparator đó cho vị trí chèn nào và kết quả nào?

**Lời giải:** chèn tại 1, giữa 9 và 7; kết quả là -2. Tìm bằng thứ tự tự nhiên trên list này vi phạm điều kiện, không được dựa vào một con số trả về cụ thể.

### Bài 5 — Phần tử trùng

List [1,3,3,3,8], tìm 3. Có được khẳng định kết quả là 1 không? lowerBound và upperBound của 3 là gì?

**Lời giải:** không được khẳng định binarySearch chọn 1; bất kỳ chỉ số hợp lệ trong nhóm 1,2,3 đều đáp ứng hợp đồng. Hai biên là 1 và 4; số phần tử bằng khóa là 3.

### Bài 6 — Compare bằng 0 nhưng equals khác

Danh sách Score được sắp theo points. Khóa tìm có tên probe, points = 20. Nếu tìm được Score tên C, points = 20, kết quả có sai vì tên khác không?

**Lời giải:** không sai đối với comparator chỉ theo points. Đó là khớp theo nhóm điểm. Nếu yêu cầu tên cũng phải khớp, cần một quan hệ tìm phù hợp hoặc kiểm tra thêm trong nhóm.

### Bài 7 — Sort ổn định và kết quả đầu tiên

Một phép sort ổn định giữ thứ tự các Score cùng điểm. Từ đó có thể suy binarySearch sẽ trả Score đầu tiên trong nhóm không?

**Lời giải:** không. Tính ổn định là hợp đồng của phép sắp, còn lựa chọn một kết quả trong nhóm là hợp đồng khác. Muốn phần tử đầu phải tìm biên đầu.

### Bài 8 — subList và mã âm

whole là [0,10,20,30,40,50], part = whole.subList(2,5) là [20,30,40]. Tìm 35 trên part trả gì và vị trí chèn tương ứng trong whole là gì?

**Lời giải:** trong part, vị trí chèn là 2 nên trả -3. Chuyển sang whole sau khi giải mã: 2 + 2 = 4. Không cộng offset 2 thẳng vào -3 rồi coi là chỉ số kết quả.

### Bài 9 — Thay thuộc tính của phần tử

List các Product được sắp theo price. Một Product ở giữa bị đổi price thành giá lớn nhất mà vị trí không đổi. Chỉ vì list không có add/remove từ lần sort, binarySearch còn chắc chắn hợp lệ không?

**Lời giải:** không. Thay thuộc tính tham gia so sánh có thể phá thứ tự dù cấu trúc list không đổi kích thước. Cần quản lý cập nhật để duy trì hoặc khôi phục thứ tự.

### Bài 10 — LinkedList và chi phí

Một LinkedList rất lớn đã sắp. Có đúng Collections.binarySearch luôn tìm trong O(log n) thời gian chỉ vì chỉ so sánh O(log n) phần tử không?

**Lời giải:** không. Truy cập/di chuyển trong cấu trúc cũng có chi phí. Hợp đồng thư viện mô tả O(n) bước đi qua liên kết ở cách tìm dựa trên iterator cho list tuần tự lớn, dù số so sánh là O(log n).

### Bài 11 — Comparator chi tiết hơn

List được sắp theo điểm rồi tên. Tìm chỉ theo điểm có nhất thiết sai điều kiện không? Còn list chỉ được sắp theo điểm mà tìm bằng điểm rồi tên thì sao?

**Lời giải:** thứ tự điểm-rồi-tên vẫn giữ không giảm theo điểm, nên tìm theo điểm có thể hợp lệ. Chiều ngược không tự bảo đảm thứ tự tên trong từng nhóm điểm; phải sắp hoặc xác minh theo quan hệ chi tiết dùng để tìm.

### Bài 12 — Nguồn bất biến về cấu trúc

Một List không cho sửa chứa các đối tượng mutable và được giữ qua unmodifiable view. Nó đã sắp theo một trường mutable. Chặn add/set qua view có đủ giữ điều kiện tìm kiếm không?

**Lời giải:** không. Chủ sở hữu nguồn hoặc người giữ phần tử còn có thể sửa trạng thái làm thay đổi quan hệ so sánh. Cần mô hình phần tử và quyền cập nhật phù hợp, không chỉ lớp bọc cấu trúc.

## 14. Tài liệu đối chiếu

- [Collections.binarySearch — điều kiện thứ tự, mã vị trí chèn và độ phức tạp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)).
- [List.sort — comparator và tính ổn định của phép sắp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).
- [Comparator — quan hệ thứ tự và sự khác nhau với equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).
- [Comparable — thứ tự tự nhiên](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).
- [RandomAccess — khả năng truy cập theo chỉ số](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html).
