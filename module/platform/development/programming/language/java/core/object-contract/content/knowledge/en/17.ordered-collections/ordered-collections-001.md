# TreeSet và TreeMap dùng phép so sánh để nhận diện khóa tương đương

## 1. Điều cần hiểu trước: thứ tự và “trùng khóa” có chung một quy tắc

Trong Java, `TreeSet<E>` và `TreeMap<K,V>` là các cấu trúc dữ liệu **có thứ tự sắp xếp** dựa trên **thứ tự tự nhiên** (`Comparable`) hoặc một **bộ so sánh** (`Comparator`). Phép so sánh ấy không chỉ quyết định phần tử nằm trước hay sau; nó còn quyết định hai khóa được xem là **tương đương để lưu trữ và tra cứu**.

Quy tắc cốt lõi:

> Với hai khóa `a`, `b` hợp lệ trong cùng cấu trúc có thứ tự, `compare(a, b) == 0` nghĩa là cấu trúc sẽ đối xử với chúng như **một khóa tương đương**.

Trong đó `compare` là `comparator.compare(a,b)` nếu cấu trúc có comparator; hoặc là kết quả của thứ tự tự nhiên qua `Comparable.compareTo` nếu không truyền comparator.

Điều này có thể khác hoàn toàn với `a.equals(b)`:

- `TreeSet` không lưu hai phần tử mà bộ so sánh đánh giá bằng `0`; `add` phần tử thứ hai trả về `false`.
- `TreeMap` xem hai khóa có kết quả so sánh `0` là cùng vị trí khóa; `put` bằng khóa thứ hai cập nhật **giá trị của mục nhập** thay vì tăng số khóa.
- `contains`, `containsKey` và `get` có thể coi một đối tượng truy vấn **khác theo `equals`** là khóa đã tồn tại nếu phép so sánh cho kết quả `0`.
- `HashSet` và `HashMap` thông thường dựa vào `hashCode` và `equals`, nên có thể đưa ra kết quả khác với `TreeSet`/`TreeMap` trên cùng dữ liệu.

Phần quan trọng nhất của bài là phân biệt **tương đương do phép so sánh** với **bằng nhau do `equals`**, biết lúc nào cần hai quan hệ nhất quán và hiểu hậu quả nếu chúng khác nhau.

## 2. Cơ chế định vị khóa trong cây có thứ tự

Hãy hình dung `TreeMap` lưu một cấu trúc cây tìm kiếm cân bằng, thường là cây đỏ-đen. Khi thêm hay tìm một khóa `query`, cấu trúc sử dụng phép so sánh với khóa của nút đang xét:

| Kết quả so sánh khóa truy vấn với khóa nút | Ý nghĩa với tìm kiếm |
| --- | --- |
| Giá trị âm | Khóa truy vấn đứng **trước** khóa nút; tiếp tục tìm nhánh thích hợp phía trước (theo thứ tự cây). |
| `0` | Hai khóa **tương đương theo thứ tự so sánh**; đã gặp khóa logic mà cấu trúc đang tìm. |
| Giá trị dương | Khóa truy vấn đứng **sau** khóa nút; tiếp tục tìm nhánh thích hợp phía sau. |

Đây là sơ đồ khái niệm, không phải mã nguồn cụ thể của `TreeMap`:

```text
search(query):
    node = root
    while node != null:
        result = compare(query, node.key)

        if result < 0:
            node = node.left
        else if result > 0:
            node = node.right
        else:
            return FOUND(node)  // result == 0: tương đương khóa
    return NOT_FOUND
```

Đối với `TreeSet`, yếu tố quyết định là cách so sánh **phần tử**; đối với `TreeMap` là cách so sánh **khóa**. Hai cấu trúc này **không dùng `hashCode` để xác định vị trí trong cây**. Chúng cũng không đòi mỗi cặp khóa khác nhau phải có mã băm khác nhau.

Ví dụ với comparator chỉ xét tên không phân biệt hoa/thường: `"Java"` và `"JAVA"` đều nằm tại một vị trí khóa vì `compare("Java","JAVA") == 0`, dù `String.equals` của chúng trả `false`.

### Dấu của `compare` mới là điều quan trọng

Theo hợp đồng `Comparator`/`Comparable`, kết quả âm, `0` và dương biểu diễn thứ tự. Không được đòi chính xác `-1` hay `1`; bộ so sánh hợp lệ có thể trả mọi số nguyên âm/dương. Viết `if (compare(a,b) == -1)` là sai cách diễn giải hợp đồng. Viết `result < 0`, `result == 0` hoặc `result > 0`.

## 3. So với HashSet và HashMap

| Cấu trúc | Điều dùng để định hướng tìm kiếm | Điều quyết định trùng khóa/phần tử |
| --- | --- | --- |
| `HashSet<E>` | `hashCode()` của phần tử | Bình đẳng theo `equals` (và kiểm tra cùng tham chiếu khi phù hợp) |
| `HashMap<K,V>` | `hashCode()` của khóa | Bình đẳng theo `equals` của khóa |
| `TreeSet<E>` | `Comparable` hoặc `Comparator` | Kết quả so sánh `0` |
| `TreeMap<K,V>` | `Comparable` hoặc `Comparator` | Kết quả so sánh `0` của khóa |

**Hai điểm cần giữ riêng:**

1. Hash trùng nhau **không chứng minh** hai khóa bằng nhau; cấu trúc băm vẫn phải so sánh bằng nhau.
2. Với cây có thứ tự, `compare(a,b) == 0` là **điều kiện nhận diện cùng khóa theo chính sách sắp xếp**, cho dù `a.equals(b)` có thể sai.

Nếu bộ so sánh “nhìn” ít thuộc tính hơn `equals`, các đối tượng khác nhau theo `equals` có thể bị gộp thành một khóa. Nếu bộ so sánh phân biệt những đối tượng mà `equals` coi là bằng nhau, cây có thể giữ hai mục mà một `HashSet` gộp thành một.

Java khuyến nghị thứ tự dùng trong sorted set/map **nhất quán với `equals`** để các cấu trúc đáp ứng kỳ vọng chung của `Set`/`Map`. Tuy nhiên API vẫn cho phép comparator không nhất quán: khi đó thao tác theo thứ tự **vẫn có cơ chế xác định**, nhưng kết quả “trùng phần tử” có thể gây bất ngờ hoặc không tuân theo hợp đồng chung dựa trên `equals`.

## 4. Ví dụ đặc trưng: chuỗi không phân biệt hoa/thường

`String.equals` phân biệt chữ hoa/thường, trong khi `String.CASE_INSENSITIVE_ORDER` là comparator sắp xếp không phân biệt hoa/thường theo quy tắc của `String.compareToIgnoreCase`.

Vì vậy:

```java
String a = "Java";
String b = "JAVA";

boolean sameByEquals = a.equals(b); // false
boolean sameByComparator =
        String.CASE_INSENSITIVE_ORDER.compare(a, b) == 0; // true
```

Đây chỉ là các biểu thức minh họa trong một phương thức, chưa phải chương trình độc lập. Nếu tạo:

```java
TreeSet<String> names =
        new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

names.add("Java"); // true
names.add("JAVA"); // false
```

`TreeSet` chỉ giữ một phần tử vì lần thêm thứ hai bị nhận diện là trùng theo comparator. Khi hỏi `names.contains("jAvA")`, kết quả là `true` dù không có chuỗi chính xác `"jAvA"` nào được thêm. Điều kiện là comparator coi truy vấn này tương đương với khóa hiện có.

Với `TreeMap`:

```java
TreeMap<String, Integer> counts =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

counts.put("Java", 1);
counts.put("JAVA", 2);
```

Cấu trúc chỉ có **một mục nhập**, và giá trị gắn với khóa tương đương được cập nhật thành `2`. Trên `TreeMap` Java, đối tượng khóa của mục nhập hiện có được giữ khi cập nhật theo khóa comparator-tương-đương; vì thế trong ví dụ khóa nhìn thấy từ `firstKey()` vẫn là `"Java"`, còn `get("java")` trả `2`. Đừng dựa vào việc thêm khóa khác kiểu chữ để thay đổi cách viết khóa đã lưu; nếu nghiệp vụ cần khóa chuẩn hóa, hãy chuẩn hóa trước khi thêm.

### Khi nào đây là chính sách hợp lý?

Trường hợp cho phép: một từ khóa tìm kiếm, nhãn đã được quy định rõ không phân biệt chữ hoa/chữ thường, hoặc tập tên theo chính sách riêng.

Trường hợp cần cân nhắc: mã sản phẩm, mã giảm giá, tài khoản, định danh bên ngoài và các chuỗi Unicode đa ngôn ngữ. Comparator không phân biệt case **không đồng nghĩa** chuẩn hóa Unicode toàn diện, loại bỏ dấu, hoặc đối chiếu ngôn ngữ theo locale. Chính sách bằng nhau của hệ thống phải được đặc tả trước.

## 5. Ví dụ khác: BigDecimal có thứ tự tự nhiên không nhất quán với equals

`BigDecimal.compareTo` so sánh **giá trị số**, trong khi `BigDecimal.equals` còn xét **scale** (với các cách biểu diễn khác scale, có thể coi là khác nhau).

Ví dụ:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

Đây là đoạn nằm trong phương thức có import `java.math.BigDecimal`. Hai giá trị số bằng nhau theo thứ tự tự nhiên nhưng **khác nhau theo `equals`**. Do đó:

- `TreeSet<BigDecimal>` dùng thứ tự tự nhiên, chỉ giữ một phần tử cho `2.0` và `2.00`.
- `HashSet<BigDecimal>` dựa vào `equals`/`hashCode`, nên giữ được cả hai.
- `TreeMap<BigDecimal, V>` xem hai số này là một khóa sắp xếp; `HashMap<BigDecimal, V>` xem chúng là hai khóa khác nhau.

Đây là đặc điểm **có chủ ý của API**, không phải lỗi của `TreeSet` hay `HashSet`. Khi chọn làm khóa, phải tự quyết định dữ liệu có cần phân biệt scale hay không.

Nếu miền nghiệp vụ coi mọi biểu diễn cùng giá trị số là một giá trị duy nhất, có thể cân nhắc chuẩn hóa biểu diễn `BigDecimal` trước khi lưu vào các collection khác nhau (ví dụ `stripTrailingZeros` nếu phù hợp chính sách). Tuy vậy `stripTrailingZeros` có thể đổi biểu diễn scale và kiểu hiển thị, nên cần kiểm tra các yêu cầu về tiền tệ, định dạng và biểu diễn dữ liệu. Không mặc định việc chuẩn hóa này luôn an toàn cho mọi domain.

## 6. Chương trình Java 17+ chạy độc lập

Chương trình dưới đây cùng lúc quan sát bốn tình huống:

1. `TreeSet` và `TreeMap` sử dụng comparator không phân biệt case, nên `"Java"` và `"JAVA"` chỉ chiếm một khóa.
2. `HashSet` của chuỗi phân biệt hai biểu diễn đó.
3. `BigDecimal` có `compareTo == 0` nhưng `equals == false`.
4. Comparator chỉ xét tuổi khiến hai `Person` khác nhau bị xem là tương đương; bổ sung tiêu chí `name` tạo thứ tự phân biệt tốt hơn cho ví dụ.

Lưu thành `TreeKeyEquivalenceDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class TreeKeyEquivalenceDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        String a = "Java";
        String b = "JAVA";

        Set<String> sortedNames =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        System.out.println("TreeSet add Java: " + sortedNames.add(a));
        System.out.println("TreeSet add JAVA: " + sortedNames.add(b));
        System.out.println("TreeSet size: " + sortedNames.size());
        System.out.println("TreeSet first: " + sortedNames.iterator().next());
        System.out.println("TreeSet contains jAvA: "
                + sortedNames.contains("jAvA"));
        System.out.println("String equals: " + a.equals(b));

        Set<String> hashedNames = new HashSet<>();
        hashedNames.add(a);
        hashedNames.add(b);
        System.out.println("HashSet size: " + hashedNames.size());

        TreeMap<String, Integer> scores =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        System.out.println("TreeMap first put old: "
                + scores.put("Java", 1));
        System.out.println("TreeMap second put old: "
                + scores.put("JAVA", 2));
        System.out.println("TreeMap size: " + scores.size());
        System.out.println("TreeMap firstKey: " + scores.firstKey());
        System.out.println("TreeMap get java: " + scores.get("java"));

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("BigDecimal compareTo: " + x.compareTo(y));
        System.out.println("BigDecimal equals: " + x.equals(y));

        Set<BigDecimal> sortedNumbers = new TreeSet<>();
        sortedNumbers.add(x);
        sortedNumbers.add(y);
        Set<BigDecimal> hashedNumbers = new HashSet<>();
        hashedNumbers.add(x);
        hashedNumbers.add(y);
        System.out.println("BigDecimal TreeSet size: "
                + sortedNumbers.size());
        System.out.println("BigDecimal HashSet size: "
                + hashedNumbers.size());

        Person an = new Person("An", 20);
        Person binh = new Person("Binh", 20);

        Comparator<Person> byAge =
                Comparator.comparingInt(Person::age);
        TreeSet<Person> sameAgeSet = new TreeSet<>(byAge);
        sameAgeSet.add(an);
        sameAgeSet.add(binh);

        System.out.println("Person equals: " + an.equals(binh));
        System.out.println("age-only compare: " + byAge.compare(an, binh));
        System.out.println("age-only TreeSet size: "
                + sameAgeSet.size());
        System.out.println("age-only contains Binh: "
                + sameAgeSet.contains(binh));

        Comparator<Person> byAgeThenName =
                Comparator.comparingInt(Person::age)
                          .thenComparing(Person::name);
        TreeSet<Person> distinctPersons =
                new TreeSet<>(byAgeThenName);
        distinctPersons.add(an);
        distinctPersons.add(binh);
        System.out.println("age+name TreeSet size: "
                + distinctPersons.size());
    }
}
```

Lệnh biên dịch và chạy (JDK 17+):

```bash
javac -encoding UTF-8 TreeKeyEquivalenceDemo.java
java TreeKeyEquivalenceDemo
```

Kết quả chính xác của chương trình:

```text
TreeSet add Java: true
TreeSet add JAVA: false
TreeSet size: 1
TreeSet first: Java
TreeSet contains jAvA: true
String equals: false
HashSet size: 2
TreeMap first put old: null
TreeMap second put old: 1
TreeMap size: 1
TreeMap firstKey: Java
TreeMap get java: 2
BigDecimal compareTo: 0
BigDecimal equals: false
BigDecimal TreeSet size: 1
BigDecimal HashSet size: 2
Person equals: false
age-only compare: 0
age-only TreeSet size: 1
age-only contains Binh: true
age+name TreeSet size: 2
```

### Phân tích những kết quả dễ gây bất ngờ

**`TreeSet add JAVA: false`:** không có nghĩa chuỗi `"JAVA"` đã nằm trong cây theo đúng tham chiếu hoặc đúng `String.equals`. Nó nghĩa là đã có phần tử tương đương với `"JAVA"` theo comparator. Vì comparator không phân biệt chữ hoa/thường, `"Java"` đủ để lần thêm thứ hai được xem là trùng.

**`TreeMap second put old: 1`:** khi thêm `"JAVA"`, map tìm thấy khóa comparator-tương-đương `"Java"`. Nó trả giá trị cũ `1` và cập nhật thành `2`. Số mục nhập vẫn bằng `1`; lệnh `get("java")` tra cứu theo cùng comparator và nhận `2`.

**`BigDecimal TreeSet size: 1` so với `HashSet size: 2`:** thứ tự tự nhiên của `BigDecimal` coi hai biểu diễn số là tương đương; `equals` và hash code của nó phân biệt scale.

**`age-only contains Binh: true`:** `Person("An",20)` và `Person("Binh",20)` khác nhau theo `record.equals`, nhưng comparator chỉ xét tuổi, cho ra `0`. Mặc dù `binh` không được lưu như phần tử riêng, truy vấn `contains(binh)` được xem là tìm thấy khóa tương đương là `an`.

**`age+name TreeSet size: 2`:** bổ sung `name` làm tiêu chí phụ đủ để phân biệt hai đối tượng của bộ dữ liệu ví dụ. Trong một domain thực, cần kiểm tra **đầy đủ các trường quyết định `equals`**; `age + name` chỉ nhất quán với `equals` nếu quy tắc bằng nhau của kiểu đó cũng dùng hai trường tương ứng.

## 7. “Nhất quán với equals” nghĩa chính xác là gì?

Một `Comparator` hoặc thứ tự tự nhiên được gọi là **nhất quán với `equals`** khi, với các đối tượng hợp lệ đang xét:

```text
compare(a, b) == 0   nếu và chỉ nếu   a.equals(b) == true
```

Đây là điều kiện cần giữa **tập cặp tương đương theo so sánh** và **tập cặp bằng nhau theo `equals`**. Nó mạnh hơn yêu cầu comparator chỉ sắp các phần tử theo một thứ tự hợp lý.

Có hai cách sai:

1. **Comparator gộp quá mức:** `compare(a,b) == 0` nhưng `a.equals(b) == false`. Ví dụ so `Person` chỉ theo tuổi. `TreeSet` mất khả năng giữ nhiều người cùng tuổi; `TreeMap` có thể ghi đè dữ liệu của người khác.
2. **Comparator phân biệt quá mức:** `a.equals(b) == true` nhưng `compare(a,b) != 0`. Ví dụ lớp có `equals` chỉ dùng `userId` nhưng comparator còn dùng thuộc tính tên hiển thị có thể khác. `TreeSet` có thể giữ hai phần tử bằng nhau theo `equals`, gây sai kỳ vọng chung của một `Set`.

Một comparator chỉ xét tuổi vẫn có thể đúng về thứ tự số học của tuổi; **sai là khi dùng nó để xác định danh tính Person** trong ứng dụng vốn định nghĩa người bằng dữ liệu khác.

Nếu mục tiêu là chỉ một người trên mỗi tuổi, comparator theo tuổi có thể phản ánh một **quy tắc khóa nghiệp vụ khác**. Khi đó nên cân nhắc biểu diễn trực tiếp khóa `age` và lưu giá trị người trong `TreeMap<Integer, Person>`, thay vì dùng `TreeSet<Person>` rồi làm người đọc hiểu nhầm rằng hai `Person` bằng nhau.

### Mối liên hệ với hợp đồng Map/Set chung

Các interface `Set`/`Map` mô tả sự hiện diện/trùng khóa theo `equals`. Nhưng `TreeSet`/`TreeMap` được thiết kế dựa trên comparator hoặc natural ordering. Tài liệu Java khuyến nghị phép so sánh **nhất quán với `equals`** nếu muốn triển khai đáp ứng đầy đủ những kỳ vọng hợp đồng đó.

Sự không nhất quán **không có nghĩa** Java buộc phải ném lỗi. Phần lớn thao tác vẫn chạy và làm đúng theo comparator, tạo ra những kết quả quan sát được như ví dụ. Rủi ro chủ yếu là **ngữ nghĩa**, đặc biệt khi đổi qua lại giữa tập/map có thứ tự và cấu trúc dựa trên hash.

## 8. Điều kiện để comparator không làm hỏng cấu trúc cây

Không phải hàm trả số nguyên nào cũng là comparator hợp lệ. Java yêu cầu các tính chất tương ứng một thứ tự nhất quán. Các nguyên tắc cốt lõi:

- **Phản đối xứng theo dấu:** `sign(compare(a,b)) == -sign(compare(b,a))`. Đổi chiều hai đối tượng phải đảo chiều quan hệ trước/sau, hoặc cả hai trả `0`.
- **Bắc cầu của thứ tự:** nếu `compare(a,b) > 0` và `compare(b,c) > 0` thì `compare(a,c) > 0`; tương tự cho chiều âm.
- **Nhất quán khi so bằng `0`:** nếu `compare(a,b) == 0`, dấu so sánh `a` với một đối tượng `z` phải giống dấu so sánh `b` với `z`. Nếu không, hai đối tượng bị coi là một khóa nhưng lại có vị trí tương quan khác nhau với các khóa khác.
- **Ổn định trong thời gian một khóa nằm trong cây:** dữ liệu làm căn cứ sắp xếp không nên thay đổi sau khi thêm, nếu cây không được cập nhật phù hợp.

Ví dụ comparator viết như sau là nguy hiểm:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Phép trừ `int` có thể **tràn số**, trả dấu sai và phá tính bắc cầu của thứ tự. Hãy dùng:

```java
Comparator<Integer> good = Integer::compare;
```

Hai đoạn trên là các biểu thức minh họa trong phương thức với import `java.util.Comparator`. Đối với đối tượng phức tạp, dùng `Comparator.comparing`, `comparingInt`, `thenComparing`, `nullsFirst`/`nullsLast` khi đúng với policy; chúng giúp mã rõ nghĩa và giảm khả năng viết sai quy tắc.

Một lỗi nghiêm trọng khác là **comparator ngẫu nhiên hoặc dựa vào thời gian**. Nếu cùng cặp khóa mỗi lần so lại cho thứ tự khác, cây không thể duy trì giả định cần thiết để tìm/đặt dữ liệu đúng.

## 9. Thiết kế comparator khớp với danh tính của domain

Trước khi chọn `TreeSet` hay `TreeMap`, hãy định nghĩa “hai khóa tương đương” bằng chính ngôn ngữ nghiệp vụ.

### Trường hợp A: khóa là một chuỗi phân biệt case

Nếu mã phân biệt chữ hoa/thường, dùng thứ tự tự nhiên của `String`. Với hai chuỗi `"Java"` và `"JAVA"`, `String.compareTo` không trả `0`, còn `String.equals` cũng `false`. Trong trường hợp này, thứ tự và quan hệ bằng nhau nhất quán theo đúng kiểu `String`.

### Trường hợp B: username không phân biệt case

Nếu username không phân biệt case, có thể dùng comparator phù hợp để thực hiện thao tác trong một `TreeMap<String,V>`, nhưng toàn hệ thống phải nhận thức rằng `String.equals` vẫn phân biệt case. Nếu cùng lúc dùng `HashMap<String,V>`, hành vi trùng khóa sẽ khác.

Một thiết kế khác là **chuẩn hóa khóa** theo chính sách đã công bố (ví dụ lowercase trong miền ký tự ASCII hợp lệ), lưu khóa chuẩn hóa trong một value object có `equals`/`hashCode` tương ứng, và dùng comparator nhất quán với chính quan hệ đó. Cách này giúp các cấu trúc băm và sắp xếp có cùng khái niệm danh tính khi ứng dụng thật sự cần thế.

Với văn bản Unicode nhiều ngôn ngữ, đừng giả định một quy tắc `equalsIgnoreCase` hoặc `toLowerCase(Locale.ROOT)` sẽ xử lý mọi trường hợp Unicode case folding, chuẩn hóa dạng tổ hợp, accent hoặc locale. Quy tắc so sánh và canonicalization phải được thiết kế, ghi rõ và kiểm thử.

### Trường hợp C: đối tượng có nhiều trường

Nếu domain record `Person(name, age)` dùng `equals` của cả hai component, comparator xét `age` rồi `name` sẽ phù hợp với **ví dụ dùng String và int không-null** nếu comparator và `equals` cùng phân biệt tên giống nhau. Nhưng nếu thêm component khác vào record, `equals` sinh tự động thay đổi mà comparator không cập nhật, tính nhất quán có thể mất.

Thay vì “sắp theo tuổi” bằng comparator để làm khóa duy nhất, cân nhắc dùng `TreeMap<Integer, List<Person>>` khi nghiệp vụ muốn **nhóm nhiều người theo tuổi**, hoặc sử dụng một khóa duy nhất đủ tiêu chí với `thenComparing` khi muốn một `TreeSet<Person>` không gộp người.

## 10. Các phép tra cứu, giới hạn khoảng và first/last đều tuân comparator

`TreeSet` và `TreeMap` thuộc họ cấu trúc có thứ tự, nên các thao tác sau cũng dựa trên quy tắc so sánh:

- `first()`/`last()` của `TreeSet`, `firstKey()`/`lastKey()` của `TreeMap` lấy cực trị **theo comparator hoặc natural ordering**, không theo thời gian thêm hay theo `equals`.
- `lower`, `floor`, `ceiling`, `higher` tìm phần tử nằm trước/gần trước/gần sau/sau theo thứ tự, với các quy tắc bao gồm hoặc loại trừ điểm ranh giới.
- `subSet`, `headSet`, `tailSet` và `subMap`, `headMap`, `tailMap` xác định các vùng khóa bằng **thứ tự comparator**. Các view này gắn với cấu trúc cơ sở và phản ánh những thay đổi được phép.
- `contains`/`containsKey` kiểm tra xem có phần tử/khóa **tương đương theo phép so sánh** không, chứ không nhất thiết gọi `equals` để xác nhận như cấu trúc băm.

Đối với comparator không phân biệt case, ranh giới truy vấn `"JAVA"` có thể tương đương với khóa đang lưu `"Java"`. Việc một đầu khoảng có được bao gồm phụ thuộc overload và cờ inclusive/exclusive, còn kết quả so sánh `0` quyết định chúng thuộc cùng mốc thứ tự.

### Độ phức tạp và nhu cầu sử dụng

`TreeMap` bảo đảm thời gian `O(log n)` cho các thao tác `containsKey`, `get`, `put` và `remove`, giả sử chi phí của một phép so sánh được xem là hằng số. `TreeSet` có thời gian `O(log n)` bảo đảm cho `add`, `remove` và `contains` theo cùng giả định. Nếu comparator tốn kém, thời gian thực còn phụ thuộc chi phí so sánh.

`HashMap`/`HashSet` thường cho thời gian kỳ vọng gần `O(1)` với phân phối hash phù hợp, nhưng không cung cấp thứ tự sắp xếp theo comparator. Nếu cần duyệt theo thứ tự, truy vấn khoảng hoặc tìm phần tử kế cận, cây có thứ tự đem lại khả năng khác biệt.

## 11. Khóa mutable, null và lỗi trong so sánh

### 11.1. Khóa thay đổi sau khi thêm vào cây

Ví dụ `TreeSet<Person>` sắp theo `person.age`. Nếu lưu đối tượng `Person` mutable rồi sửa tuổi mà không xóa và chèn lại, thứ tự nội tại của cây vẫn được xây theo giá trị cũ. Kết quả `contains`, `remove`, truy vấn khoảng hoặc thứ tự duyệt có thể bất thường.

Tương tự với `TreeMap` nếu khóa mutable thay đổi trường được comparator dùng. **Cấu trúc cây không tự theo dõi thay đổi trong đối tượng khóa**. Nên dùng khóa bất biến; khi cần thay đổi khóa logic, thường phải xóa mục nhập theo khóa cũ và thêm lại bằng khóa mới.

### 11.2. Null và khóa không thể so sánh

Khi dùng **natural ordering**, `TreeSet`/`TreeMap` thường không chấp nhận khóa `null` vì không thể so sánh tự nhiên, và có thể ném `NullPointerException`. Với comparator riêng có xử lý `null` (ví dụ `Comparator.nullsFirst`) và chính sách phù hợp, có thể cho phép khóa `null` trong `TreeMap`/`TreeSet`.

`TreeMap` có thể cho phép **giá trị** `null`, độc lập với vấn đề khóa `null`. Khi `get(key)` trả `null`, muốn phân biệt không có khóa với có khóa nhưng giá trị `null`, dùng `containsKey(key)`.

Nếu dùng natural ordering mà các đối tượng không triển khai `Comparable` phù hợp, hoặc chúng không so sánh được với nhau, thao tác trên tree có thể ném `ClassCastException`. Comparator nên xác định rõ miền kiểu và không đưa các kiểu không tương thích vào cấu trúc.

### 11.3. Comparator có tác dụng phụ

Không để `compare` thay đổi trạng thái khóa, ghi database, gọi dịch vụ ngoài hoặc thay đổi kết quả theo lần gọi. Cấu trúc có thể cần nhiều phép so sánh trong một thao tác, và không có hợp đồng rằng comparator chỉ được gọi đúng một lần cho mỗi cặp.

Comparator sử dụng thuộc tính phụ thuộc môi trường (timezone, locale hiện hành có thể đổi, trạng thái cấu hình thay đổi) cũng khiến thứ tự thiếu ổn định. Xác định chính sách so sánh nhất quán trong suốt thời gian dùng cấu trúc; nếu thay đổi chính sách, xây lại cấu trúc theo comparator mới.

## 12. Những lỗi thường gặp

| Lỗi | Tác động quan sát được | Cách giải quyết |
| --- | --- | --- |
| Tưởng `TreeSet` chỉ loại trùng khi `equals` đúng | Có thể mất các đối tượng khác nhau nếu comparator trả `0`. | Kiểm tra `compare(a,b) == 0` có phản ánh đúng danh tính logic không. |
| Dùng comparator chỉ theo một trường như tuổi | Mọi đối tượng cùng tuổi bị xem là một phần tử, dù tên/ID khác. | Thêm tiêu chí phân biệt phù hợp hoặc dùng `TreeMap<Age,List<Person>>` để nhóm. |
| Gọi `TreeMap.put(k2,v2)` với khóa cùng comparator và nghĩ sẽ thêm mục mới | Giá trị cũ bị thay thế, map không tăng kích thước. | Đặc tả trùng khóa; dùng đủ tiêu chí khóa. |
| Nghĩ `TreeSet` và `HashSet` luôn có cùng số phần tử trên một bộ dữ liệu | `compare==0` có thể không tương ứng với `equals`. | Chọn bộ so sánh nhất quán hoặc chấp nhận chủ ý sự khác biệt. |
| So sánh chỉ với `result == -1`/`result == 1` | Hiểu sai kết quả comparator hợp lệ trả trị tuyệt đối lớn hơn 1. | So dấu âm/0/dương. |
| Viết comparator bằng phép trừ số nguyên | Tràn số có thể làm sai thứ tự, phá hợp đồng. | Dùng `Integer.compare`, `Long.compare` hoặc comparator built-in. |
| Comparator dùng trường mutable hoặc phụ thuộc đồng hồ | Cây có thể không tìm được khóa hoặc duyệt theo thứ tự sai. | Dùng khóa bất biến và chính sách so sánh ổn định. |
| Dùng `String.CASE_INSENSITIVE_ORDER` cho mọi chuỗi Unicode và kỳ vọng quy tắc locale cụ thể | Có thể gộp hoặc phân biệt dữ liệu ngoài mong muốn. | Định nghĩa chuẩn hóa/locale rõ và kiểm thử với dữ liệu thật. |
| Dùng `BigDecimal` rồi bất ngờ khi `TreeSet` và `HashSet` khác nhau | `compareTo` bỏ qua khác biệt scale mà `equals` xét đến. | Quy định khóa theo giá trị số hay theo biểu diễn; chuẩn hóa khi phù hợp. |
| Mong `hashCode` ảnh hưởng đến `TreeMap` | Cây định hướng theo comparator, hash không quyết định nhánh. | Dùng đúng mô hình cơ chế của collection. |
| Đổi comparator sau khi đã lưu phần tử | Thứ tự trong cây không tự cập nhật theo policy mới. | Tạo cấu trúc mới với comparator mới rồi nạp lại dữ liệu. |

## 13. Kiểm thử để xác nhận hợp đồng và chính sách nghiệp vụ

Khi thiết kế comparator cho một kiểu khóa riêng, cần kiểm tra **thứ tự** và **ngữ nghĩa trùng khóa**:

1. **Dấu so sánh:** nếu `compare(a,b) < 0`, thì `compare(b,a) > 0`. Kiểm tra cả trường hợp bằng `0` và các giá trị biên.
2. **Bắc cầu:** với nhiều bộ ba, nếu `a < b` và `b < c` theo comparator, thì `a < c`. Cả các bộ ba có giá trị comparator `0` cũng cần nhất quán.
3. **Tương đương qua comparator:** nếu `compare(a,b) == 0`, kiểm tra truy vấn `contains(b)`/`get(b)` khi đã lưu `a`; xác nhận behavior đúng nghiệp vụ.
4. **Nhất quán với `equals`:** với các cặp cùng ID, khác ID, cùng tiêu chí phụ và khác tiêu chí phụ, so cả `compare==0` lẫn `equals`. Nếu hai quan hệ khác nhau, tài liệu phải ghi rõ vì sao.
5. **Khả năng trùng:** thêm hai khóa cùng comparator trong `TreeSet` phải không tăng kích thước; `TreeMap.put` phải cập nhật giá trị tương ứng.
6. **Khác biệt với cấu trúc băm:** khi mong đợi semantics giống nhau, dùng cùng dữ liệu để so kích thước/khóa giữa `TreeSet` và `HashSet`; nếu khác nhau, tìm cặp khiến hai quan hệ bất đồng.
7. **Khóa mutable:** đảm bảo thuộc tính dùng để so sánh không bị sửa trong lúc còn ở tree. Nếu có giao diện thay khóa, test quy trình xóa khóa cũ và thêm khóa mới.
8. **Các biên null và kiểu:** kiểm tra chính sách `null`, giá trị đầu khoảng, ký tự Unicode, case và các mức số học lớn/nhỏ.
9. **Thao tác vùng khóa:** test `floor`, `ceiling`, `subSet`/`subMap` với khóa so sánh bằng `0` để bảo đảm ranh giới đúng.
10. **Chi phí và ổn định:** comparator phải có tính xác định, không dựa I/O và không đổi kết quả trong cùng trạng thái khóa.

Với domain quan trọng, có thể dùng property-based tests sinh nhiều bộ đôi/bộ ba và kiểm thử cả tính chất quan hệ thứ tự. Một ví dụ đơn lẻ chạy đúng chưa chứng minh toàn bộ comparator có hợp đồng hợp lệ.

## 14. Ghi nhớ

`TreeSet` và `TreeMap` dùng **thứ tự tự nhiên hoặc `Comparator`** để vừa tìm vị trí trong cây vừa **xác nhận khóa tương đương bằng kết quả so sánh `0`**. Đây là điểm khác với `HashSet` và `HashMap` vốn dựa trên hợp đồng `equals`/`hashCode`. Khi `compare(a,b)==0` không trùng với `a.equals(b)`, các collection có thể cho số phần tử và kết quả tra cứu khác nhau; ví dụ điển hình là chuỗi so không phân biệt case và `BigDecimal` khác scale. Hãy xác định rõ danh tính khóa, chọn comparator đáp ứng quan hệ đó, đảm bảo thứ tự hợp lệ và ổn định, ưu tiên khóa bất biến, rồi kiểm thử cả hành vi thêm, tra cứu, ghi đè và truy vấn khoảng.