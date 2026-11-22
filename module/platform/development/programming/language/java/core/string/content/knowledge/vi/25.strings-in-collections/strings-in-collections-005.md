# Comparator không phân biệt hoa–thường và quan hệ với equals khi lưu String trong Collection

## 1. Vấn đề và mục tiêu

Khi đưa các chuỗi Java vào collection, ta thường muốn sắp xếp **không phân biệt chữ hoa và chữ thường**. Java cung cấp sẵn `String.CASE_INSENSITIVE_ORDER`, một `Comparator<String>` cho mục đích đó. Nhưng một bẫy quan trọng xuất hiện khi dùng comparator này làm **quy tắc xác định khóa trùng nhau** trong `TreeSet` và `TreeMap`:

> **`compare(a, b) == 0` không đồng nghĩa với `a.equals(b)`.**

Ví dụ với `"Java"` và `"java"`:

- `"Java".equals("java")` là `false` vì `String.equals` so sánh nội dung có phân biệt hoa/thường.
- `"Java".equalsIgnoreCase("java")` là `true`.
- `String.CASE_INSENSITIVE_ORDER.compare("Java", "java")` là `0`: hai chuỗi tương đương **theo comparator**.
- `"Java".compareToIgnoreCase("java")` cũng là `0`.

Nếu chỉ sắp xếp để hiển thị, hành vi trên thường đúng mong muốn. Nếu dùng nó để quyết định **phần tử nào được phép tồn tại** trong tập hợp hoặc **khóa nào được coi là cùng một khóa**, hậu quả có thể là mất một biến thể chữ hoa/thường.

Bài học này làm rõ quan hệ giữa `Comparator`, `String.equals`, `equalsIgnoreCase` và cách các collection sử dụng chúng.

## 2. Các phép so sánh String cần phân biệt

| API | Kết quả/ý nghĩa | Có phân biệt hoa–thường? |
| --- | --- | --- |
| `a.equals(b)` | Hai chuỗi có nội dung giống hệt nhau theo `String.equals` | Có |
| `a.equalsIgnoreCase(b)` | Kiểm tra tương đương bỏ qua hoa–thường theo quy tắc của `String` | Không |
| `a.compareTo(b)` | So sánh thứ tự tự nhiên; trả số âm, 0 hoặc số dương | Có |
| `a.compareToIgnoreCase(b)` | So sánh thứ tự bỏ qua hoa–thường | Không |
| `String.CASE_INSENSITIVE_ORDER.compare(a,b)` | `Comparator<String>` tương ứng so sánh không phân biệt hoa–thường | Không |

`Comparator.compare(a,b)` trả giá trị **âm** nếu `a` đứng trước `b`, **0** nếu tương đương theo comparator, và **dương** nếu `a` đứng sau `b`. Khi kiểm thử, đừng phụ thuộc độ lớn cụ thể của số âm/dương; chỉ phụ thuộc vào **dấu của kết quả**.

Với `String.CASE_INSENSITIVE_ORDER`, kết quả tương thích với `compareToIgnoreCase`. Hai chuỗi khác nhau về chữ hoa/thường có thể so sánh bằng 0 dù `equals` trả về `false`. Đây gọi là comparator **không nhất quán với equals** (*inconsistent with equals*).

Điều quan trọng: `equalsIgnoreCase` là một phép thử riêng dành cho `String`; nó **không thay đổi** cách `String.equals` hay `hashCode` hoạt động. Chỉ vì truyền comparator cho một collection không có nghĩa là các loại collection khác cũng tự dùng quy tắc tương đương ấy.

## 3. Vì sao tính nhất quán với equals quan trọng?

Theo quy ước của Java, comparator được gọi là **nhất quán với equals** nếu, đối với mọi đối tượng thích hợp `a` và `b`:

~~~text
compare(a, b) == 0   khi và chỉ khi   a.equals(b) == true
~~~

Với hai chuỗi khác kiểu chữ `"Java"` và `"java"`, comparator bỏ qua hoa–thường vi phạm điều kiện này:

~~~text
String.equals:                  false
String.CASE_INSENSITIVE_ORDER:      0
~~~

Một comparator không nhất quán với equals **vẫn có thể sắp xếp hợp lệ** và được `TreeSet`/`TreeMap` chấp nhận. Nhưng `SortedSet`/`SortedMap` nói chung cần comparator nhất quán với equals để bảo đảm trọn vẹn kỳ vọng của hợp đồng `Set`/`Map`. Nếu không, tập hợp hoặc ánh xạ có thể cư xử khác `HashSet`/`HashMap` khi người dùng cho rằng mọi collection đều xác định trùng lặp giống `equals`.

**Điểm chính cần nhớ:** thuật toán của `TreeSet` và `TreeMap` dựa trên **`compare(...) == 0` để xác định khóa tương đương**. Còn `HashSet` và `HashMap` sử dụng `equals` kết hợp `hashCode` của khóa. Hai nhóm collection có thể chứa số phần tử khác nhau với cùng đầu vào.

## 4. TreeSet và HashSet khác nhau thế nào?

Đoạn sau là **mảnh mã minh họa** có thể đặt trong `main` sau khi import `java.util.*`:

~~~java
Set<String> hash = new HashSet<>();
hash.add("Java");
hash.add("java");
hash.add("JAVA");
// hash.size() == 3

Set<String> tree = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
tree.add("Java");
tree.add("java");
tree.add("JAVA");
// tree.size() == 1
// tree.contains("JAVA") == true
~~~

Với `HashSet`, ba chuỗi có nội dung khác nhau theo `equals` và được coi là ba phần tử khác nhau; `HashSet` không sắp xếp các phần tử.

Với `TreeSet`, ba chuỗi so sánh bằng 0 theo comparator không phân biệt hoa–thường, nên chỉ một phần tử đại diện được lưu. Thông thường phần tử được thêm thành công trước tiên là phần tử được giữ: nếu thêm `"Java"` đầu tiên, việc thêm `"java"` hay `"JAVA"` không thay nội dung chuỗi đang lưu. Phép `contains("JAVA")` trả về `true` vì nó sử dụng quy tắc tương đương của cây; điều này **không chứng minh** chuỗi `"JAVA"` thực sự được lưu như một đối tượng riêng.

Nếu yêu cầu nghiệp vụ là “danh sách từ khóa không phân biệt hoa thường, mỗi từ chỉ tồn tại một lần”, `TreeSet<>(String.CASE_INSENSITIVE_ORDER)` có thể đúng mong muốn. Nếu cần lưu **cả hai biến thể** `"Java"` và `"java"`, comparator đó không phù hợp để làm duy nhất khóa.

## 5. TreeMap và HashMap: khóa tương đương có thể ghi đè giá trị

Tương tự với `TreeMap`:

~~~java
TreeMap<String, Integer> map =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

map.put("Java", 1);
map.put("java", 2);

// map.size() == 1
// map.get("JAVA") == 2
// map.firstKey().equals("Java") == true
~~~

Lần `put` thứ hai không sinh một khóa độc lập vì comparator nói rằng `"Java"` và `"java"` tương đương. Giá trị gắn với khóa đã có được **thay từ 1 thành 2**. Trong trường hợp này, đối tượng/chuỗi khóa được giữ trong cây vẫn là `"Java"`, tức chính khóa của lần thêm đầu. Phép tra cứu bằng `"JAVA"` vẫn lấy được giá trị vì `TreeMap` cũng dùng comparator để tìm kiếm.

Ngược lại, với `HashMap<String,Integer>`, các khóa `"Java"` và `"java"` khác nhau theo `equals`; có thể có hai entry và tra cứu `get("JAVA")` sẽ trả `null` nếu không có entry trùng đúng `"JAVA"`.

**Hệ quả thiết kế:** trước khi sử dụng `TreeMap`/`TreeSet`, hãy xác định rõ “trùng khóa” được định nghĩa bằng **`String.equals`** hay **so sánh không phân biệt hoa–thường**. Đây là lựa chọn về **quy tắc định danh**, không chỉ về thứ tự hiển thị.

## 6. Code Java 17+ đầy đủ để kiểm chứng

Tạo tệp **CaseInsensitiveComparatorDemo.java**:

~~~java
import java.util.*;

public class CaseInsensitiveComparatorDemo {
    private static int passed;

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
        passed++;
    }

    public static void main(String[] args) {
        Comparator<String> insensitive = String.CASE_INSENSITIVE_ORDER;
        String first = "Java";
        String second = "java";

        check(insensitive.compare(first, second) == 0, "compare");
        check(first.compareToIgnoreCase(second) == 0, "compareToIgnoreCase");
        check(first.equalsIgnoreCase(second), "equalsIgnoreCase");
        check(!first.equals(second), "equals distinguishes case");

        Set<String> hash = new HashSet<>();
        hash.add("Java");
        hash.add("java");
        hash.add("JAVA");
        check(hash.size() == 3, "HashSet uses equals/hashCode");

        NavigableSet<String> folded = new TreeSet<>(insensitive);
        folded.add("Java");
        folded.add("java");
        folded.add("JAVA");
        check(folded.size() == 1, "TreeSet comparator equality");
        check(folded.contains("JAVA"), "TreeSet contains by comparator");

        NavigableMap<String, Integer> treeMap = new TreeMap<>(insensitive);
        treeMap.put("Java", 1);
        treeMap.put("java", 2);
        check(treeMap.size() == 1, "TreeMap key equivalence");
        check(treeMap.get("JAVA") == 2, "TreeMap lookup");
        check(treeMap.firstKey().equals("Java"), "original key retained");

        Comparator<String> insensitiveThenExact =
                String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder());
        TreeSet<String> distinct = new TreeSet<>(insensitiveThenExact);
        distinct.add("Java");
        distinct.add("java");
        distinct.add("JAVA");
        check(distinct.size() == 3, "tie breaker keeps distinct keys");
        check(distinct.toString().equals("[JAVA, Java, java]"),
                "tie breaker ordering");
        check(insensitiveThenExact.compare(first, second) != 0,
                "not comparator-equal if !equals");

        List<String> orderedList = new ArrayList<>(List.of("b", "A", "a", "B"));
        orderedList.sort(insensitive);
        check(orderedList.equals(List.of("A", "a", "b", "B")),
                "List.sort stable with ties");

        check(insensitive.compare("I", "\u0131") == 0,
                "Unicode case matching differs from locale conventions");

        System.out.println("equals=" + first.equals(second));
        System.out.println("ignoreCaseCompare=" + insensitive.compare(first, second));
        System.out.println("HashSet.size=" + hash.size());
        System.out.println("TreeSet.size=" + folded.size());
        System.out.println("TreeMap.size=" + treeMap.size());
        System.out.println("TreeMap.get(JAVA)=" + treeMap.get("JAVA"));
        System.out.println("TieBreakerSet=" + distinct);
        System.out.println("SortedList=" + orderedList);
        System.out.println("PASS: " + passed + " checks");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CaseInsensitiveComparatorDemo.java
java CaseInsensitiveComparatorDemo
~~~

Đầu ra chính xác:

~~~text
equals=false
ignoreCaseCompare=0
HashSet.size=3
TreeSet.size=1
TreeMap.size=1
TreeMap.get(JAVA)=2
TieBreakerSet=[JAVA, Java, java]
SortedList=[A, a, b, B]
PASS: 15 checks
~~~

Chương trình kiểm tra 15 giả định bằng `check`; nếu kết quả khác mong đợi, nó ném `AssertionError` và không in dòng cuối `PASS`. Việc kiểm tra `equals`, `compareToIgnoreCase` và comparator cạnh nhau giúp thấy rõ các phép so sánh thực sự khác nhau ở đâu.

`List.sort` ở ví dụ còn kiểm tra **tính ổn định (stable sort)**: chuỗi `"A"` và `"a"` so sánh bằng 0 với comparator nên giữ thứ tự tương đối như trong danh sách đầu. Tương tự, `"b"` và `"B"` giữ thứ tự tương đối. `List.sort` dùng comparator để sắp xếp **nhưng không loại phần tử trùng theo comparator**.

## 7. Cách sắp xếp không phân biệt hoa–thường mà vẫn giữ tất cả biến thể

Nếu cần ưu tiên nhóm các chuỗi theo chữ hoa/thường nhưng vẫn cho phép từng chuỗi **khác nhau theo `equals`** tồn tại trong `TreeSet`, thêm một tiêu chí so sánh phụ (*tie-breaker*):

~~~java
Comparator<String> byCaseInsensitiveThenExact =
        String.CASE_INSENSITIVE_ORDER
              .thenComparing(Comparator.naturalOrder());

TreeSet<String> set = new TreeSet<>(byCaseInsensitiveThenExact);
set.add("Java");
set.add("java");
set.add("JAVA");
// 3 phần tử theo thứ tự: [JAVA, Java, java]
~~~

Quy tắc hoạt động:

1. So sánh **không phân biệt hoa–thường** trước để nhóm các chuỗi cùng cách viết khi bỏ qua hoa/thường.
2. Khi kết quả bước một bằng 0, so sánh tiếp theo **thứ tự tự nhiên của String** (có phân biệt hoa–thường).
3. Cuối cùng, kết quả bằng 0 **chỉ khi hai String có cùng nội dung theo equals**. Vì vậy comparator kết hợp này nhất quán với `String.equals`.

Nhờ tiêu chí thứ hai, `"JAVA"`, `"Java"`, `"java"` đều được giữ trong `TreeSet` dù nằm gần nhau trong thứ tự sắp xếp. Đây là lựa chọn phù hợp nếu **sắp xếp bỏ qua hoa/thường** là nhu cầu hiển thị nhưng **duy nhất khóa theo equals** vẫn phải được duy trì.

Nếu cần bảo toàn **thứ tự chèn**, hãy dùng collection có tính chất tương ứng (ví dụ `LinkedHashSet`); không nên chọn `TreeSet` chỉ vì nó có thể nhận comparator.

## 8. Lựa chọn khác: sắp xếp List không làm biến mất chuỗi

Với `List`, có thể sắp xếp không phân biệt hoa/thường mà **giữ tất cả phần tử**, kể cả khi comparator trả 0:

~~~java
List<String> names = new ArrayList<>(
        List.of("b", "A", "a", "B"));
names.sort(String.CASE_INSENSITIVE_ORDER);
// [A, a, b, B]
~~~

`List.sort` thực hiện sắp xếp ổn định, nên các phần tử bằng nhau theo comparator giữ thứ tự tương đối; không có bước “deduplicate”. Vì thế khi yêu cầu là **chỉ sắp xếp**, một `List` có thể là cấu trúc phù hợp hơn `TreeSet` hoặc `TreeMap`.

Khi cần vừa **bỏ trùng** vừa sắp xếp, hãy định nghĩa hai yêu cầu riêng: bỏ trùng theo `equals` hay theo cách bỏ qua hoa/thường? Sắp xếp bằng comparator nào? Có thể cần một cấu trúc lưu khóa và một danh sách hiển thị riêng.

## 9. Unicode, ngôn ngữ và giới hạn của “không phân biệt hoa–thường”

`String.CASE_INSENSITIVE_ORDER` là quy tắc so sánh của `String` và **không sử dụng locale của người dùng** để xác định thứ tự ngôn ngữ tự nhiên. Ví dụ với chữ `I` ASCII và chữ `ı` (Latin small dotless i, U+0131), Java có thể coi chúng là tương đương khi bỏ qua hoa/thường:

~~~java
boolean same =
        String.CASE_INSENSITIVE_ORDER.compare("I", "\u0131") == 0;
// same == true
~~~

Điều này **không có nghĩa** comparator tạo ra thứ tự từ điển đúng cho mọi ngôn ngữ. Với danh sách tên người, tiêu đề hoặc từ vựng cần sắp xếp theo quy tắc ngôn ngữ cụ thể, hãy xem xét `java.text.Collator` được tạo cho một `Locale` phù hợp, và kiểm thử các quy tắc chữ cái/dấu của ngôn ngữ mục tiêu. `Collator` cũng có thể coi nhiều chuỗi khác nhau theo `equals` là tương đương; khi dùng trong `TreeSet`/`TreeMap` vẫn cần quyết định rõ ý nghĩa của `compare == 0`.

Không nên mặc định thay comparator bằng cách đưa toàn bộ chuỗi qua `toLowerCase()` hoặc `toUpperCase()` mà không chọn locale và không kiểm tra Unicode. Các phép chuyển đổi chữ hoa/thường có thể phụ thuộc ngôn ngữ, có thể làm thay đổi độ dài chuỗi và không nhất thiết tạo đúng cùng quan hệ tương đương với `equalsIgnoreCase`. Nếu mục tiêu chỉ là thứ tự bỏ qua hoa/thường theo Java, dùng comparator sẵn có sẽ trực tiếp và rõ ràng hơn.

## 10. Những lỗi thường gặp

1. **Nghĩ `compare(...) == 0` luôn tương đương với `equals`:** sai với `String.CASE_INSENSITIVE_ORDER`. Kiểm thử cả hai phép so sánh.
2. **Chuyển từ `HashSet` sang `TreeSet` nhưng không xét quy tắc trùng:** có thể làm biến mất các biến thể khác nhau chỉ về chữ hoa/thường.
3. **Cho rằng `TreeMap.put` với khóa khác kiểu chữ luôn thêm entry:** nó có thể ghi đè giá trị của entry cũ.
4. **Nhìn thấy `TreeSet.contains("JAVA") == true` rồi nghĩ phần tử `"JAVA"` đã được thêm:** cây tra cứu theo comparator; nó có thể chỉ đang chứa `"Java"`.
5. **Thêm tie-breaker khi nghiệp vụ thật sự muốn bỏ trùng không phân biệt hoa/thường:** tie-breaker sẽ khiến `"Java"` và `"java"` cùng tồn tại, trái với mong muốn loại trùng.
6. **Cho rằng comparator không phân biệt hoa/thường đồng nghĩa với thứ tự đúng cho mọi locale:** cần kiểm thử Unicode và cân nhắc `Collator` khi yêu cầu về ngôn ngữ quan trọng.
7. **Dùng `hashCode` làm tie-breaker cho khóa String:** giá trị băm có thể va chạm, không bảo đảm `compare == 0` đúng khi và chỉ khi `equals`; dùng `String.compareTo`/`naturalOrder` làm tiêu chí phụ.

## 11. Bài tập kiểm tra hiểu biết

**Bài 1.** `new TreeSet<>(String.CASE_INSENSITIVE_ORDER)` lần lượt nhận `"A"`, `"a"`, `"B"`. Tập có bao nhiêu phần tử?

Đáp án: **2**. `"A"` và `"a"` tương đương theo comparator nên chỉ có một đại diện; `"B"` khác với chúng.

**Bài 2.** `new HashSet<String>()` lần lượt nhận `"A"` và `"a"`. Kích thước là bao nhiêu?

Đáp án: **2** vì `String.equals` phân biệt hoa/thường.

**Bài 3.** Tại sao comparator `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` giữ được cả `"A"` và `"a"` trong `TreeSet`?

Đáp án: khi so sánh không phân biệt hoa/thường hòa nhau, tiêu chí thứ hai so sánh có phân biệt hoa/thường và cho kết quả khác 0. Hai chuỗi không bị coi là cùng một khóa.

**Bài 4.** Khi nào nên dùng comparator không phân biệt hoa/thường **không có tie-breaker**?

Đáp án: khi **chính nghiệp vụ quy định** mọi biến thể hoa/thường của một chuỗi là **cùng một khóa**. Khi chỉ cần thứ tự hiển thị, nên sắp xếp `List` hoặc thêm tie-breaker tùy cấu trúc dữ liệu.

## 12. Ghi nhớ

- `String.equals` và `String.hashCode` xác định tương đương **phân biệt hoa/thường** cho `HashSet` và `HashMap`.
- `String.CASE_INSENSITIVE_ORDER` và `compareToIgnoreCase` tạo quan hệ tương đương **không phân biệt hoa/thường**; `compare == 0` có thể xuất hiện với hai chuỗi `equals == false`.
- `TreeSet`/`TreeMap` dùng comparator để quyết định khóa trùng, nên lựa chọn comparator ảnh hưởng trực tiếp đến **dữ liệu được giữ**.
- Nếu cần **sắp xếp** không phân biệt hoa/thường và **giữ mọi String khác nhau theo equals**, dùng comparator chính bỏ qua hoa/thường rồi `thenComparing(Comparator.naturalOrder())`.
- Nếu cần thứ tự theo ngôn ngữ, đánh giá `Collator` theo locale và tiếp tục xem xét tính nhất quán với `equals`.

Hãy quyết định rõ **khái niệm “hai String là cùng một khóa”** trước khi chọn cấu trúc collection và comparator. Đây là yếu tố quyết định tính đúng đắn của chương trình, không đơn thuần là cách sắp xếp chữ.
