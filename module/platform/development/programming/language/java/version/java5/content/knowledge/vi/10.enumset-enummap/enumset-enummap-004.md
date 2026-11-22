# Phép hợp, giao và hiệu trên EnumSet

## 1. Khái niệm: kết hợp các tập hằng enum

`EnumSet` biểu diễn một tập các hằng thuộc cùng một kiểu enum. Khi cần kết hợp các nhóm lựa chọn, ba phép toán cơ bản là:

- **Hợp**: lấy phần tử thuộc ít nhất một trong hai tập.
- **Giao**: chỉ giữ phần tử có ở cả hai tập.
- **Hiệu A trừ B**: giữ phần tử có trong A nhưng không có trong B.

Ví dụ miền giá trị:

```java
// Khai báo minh họa.
enum Capability {
    READ,
    WRITE,
    DELETE,
    EXECUTE
}
```

Cho:

```text
A = {READ, WRITE}
B = {WRITE, DELETE}
```

Ta có:

| Phép toán | Ký hiệu | Kết quả |
| --- | --- | --- |
| Hợp | `A ∪ B` | `{READ, WRITE, DELETE}` |
| Giao | `A ∩ B` | `{WRITE}` |
| Hiệu A trừ B | `A \ B` | `{READ}` |
| Hiệu B trừ A | `B \ A` | `{DELETE}` |

Phép hiệu có hướng: đổi thứ tự hai tập có thể đổi kết quả. Đây là sự khác nhau quan trọng nhất với hợp và giao.

Các phép toán và API dưới đây vẫn dùng trong Java hiện đại; chương trình thực hành chạy trên Java 17 trở lên.

## 2. Ánh xạ phép toán sang phương thức

`EnumSet` dùng những thao tác collection quen thuộc:

| Phương thức gọi trên tập nhận | Tác dụng lên tập nhận |
| --- | --- |
| `addAll(other)` | Hợp với `other` |
| `retainAll(other)` | Giữ giao với `other` |
| `removeAll(other)` | Loại phần có trong `other`, tạo hiệu theo chiều tập nhận trừ đối số |

Điểm cần nhớ: các phương thức này **sửa tập nhận lời gọi**. Chúng không tự trả về một `EnumSet` mới.

```java
// Minh họa trong một phương thức; cần import java.util.EnumSet.
EnumSet<Capability> working = EnumSet.of(Capability.READ);
boolean changed = working.addAll(EnumSet.of(Capability.WRITE));
```

Sau lời gọi:

- `working` chứa `READ` và `WRITE`.
- `changed` là `true` vì tập đã thay đổi.

Giá trị trả về là `boolean` cho biết tập nhận có thay đổi hay không, không phải chính tập kết quả.

Vì vậy, cách viết sau không biên dịch:

```java
// Minh họa lỗi kiểu trả về.
EnumSet<Capability> result = working.addAll(other);
```

Muốn có một kết quả riêng, tạo bản sao rồi áp dụng thao tác lên bản sao.

## 3. Phép hợp: addAll

Hợp trả lời câu hỏi: “Có ở A hoặc có ở B?”

```java
// Minh họa trong một phương thức có hai EnumSet<Capability> a, b.
EnumSet<Capability> union = EnumSet.copyOf(a);
union.addAll(b);
```

Với A và B ở đầu bài:

```text
union = [READ, WRITE, DELETE]
```

`WRITE` có ở cả hai đầu vào nhưng chỉ xuất hiện một lần vì kết quả vẫn là tập hợp.

Cách dùng thường gặp là gộp các nhóm khả năng hoặc lựa chọn từ nhiều nguồn. Không cần tự duyệt từng hằng để loại trùng.

Nếu cố ý muốn sửa A tại chỗ, có thể gọi `a.addAll(b)`. Điều quan trọng là hợp đồng phương thức hoặc tên biến phải thể hiện rõ quyền sửa đổi ấy, tránh làm người gọi tưởng A được giữ nguyên.

## 4. Phép giao: retainAll

Giao trả lời câu hỏi: “Phần tử nào có ở cả A và B?”

```java
// Minh họa trong một phương thức.
EnumSet<Capability> intersection = EnumSet.copyOf(a);
intersection.retainAll(b);
```

Với ví dụ:

```text
intersection = [WRITE]
```

Thao tác giữ lại những thành viên của tập nhận cũng xuất hiện trong đối số, đồng thời bỏ những thành viên khác.

Một tình huống sử dụng là tìm những lựa chọn vừa được yêu cầu vừa được một thành phần hỗ trợ. Phép toán chỉ xử lý quan hệ thành viên; ý nghĩa nghiệp vụ của từng nhóm cần được đặt tên rõ ở nơi gọi.

Đừng nhầm `retainAll` với `containsAll`:

- `retainAll` có thể sửa tập nhận để giữ phần giao.
- `containsAll` chỉ kiểm tra tập nhận có chứa toàn bộ phần tử của đối số hay không.

Kết quả `boolean` của `retainAll` là “tập có thay đổi không?”, không phải “hai tập có giao nhau không?”. Nếu tập nhận đã nằm hoàn toàn trong đối số, `retainAll` có thể trả về `false` dù giao không rỗng.

## 5. Phép hiệu: removeAll và hướng phép toán

Hiệu A trừ B trả lời: “Phần tử nào thuộc A nhưng không thuộc B?”

```java
// Minh họa trong một phương thức.
EnumSet<Capability> aMinusB = EnumSet.copyOf(a);
aMinusB.removeAll(b);
```

Kết quả:

```text
aMinusB = [READ]
```

Đổi chiều:

```java
// Minh họa trong một phương thức.
EnumSet<Capability> bMinusA = EnumSet.copyOf(b);
bMinusA.removeAll(a);
```

Kết quả:

```text
bMinusA = [DELETE]
```

`removeAll` không đưa các phần tử chỉ có ở B vào kết quả. Nó chỉ loại phần giao khỏi tập nhận.

Một cách đặt tên hữu ích trong ứng dụng là `remaining`, `unsupported` hoặc `removedFromSelection`, tùy ý nghĩa cụ thể, thay vì một tên chung khó nhận ra chiều phép trừ.

### Hiệu không phải phần bù

Phần bù của B theo toàn bộ miền `Capability` là `{READ, EXECUTE}`. Nhưng A trừ B chỉ là `{READ}`, vì `EXECUTE` vốn không thuộc A.

`EnumSet.complementOf(b)` xét tất cả hằng của kiểu enum. Nó không thay thế cho `a.removeAll(b)` trên một bản sao của A.

### Hiệu cũng không phải hiệu đối xứng

Hiệu đối xứng giữ phần chỉ xuất hiện ở một trong hai tập:

```text
(A \ B) ∪ (B \ A) = {READ, DELETE}
```

Nó khác cả hợp lẫn hiệu có hướng. Khi đề bài nói “hiệu”, phải xác định có yêu cầu thêm chữ “đối xứng” hay không.

## 6. Sao chép để giữ nguyên đầu vào

Một lỗi phổ biến:

```java
// Minh họa có tác dụng phụ nếu mục đích là giữ nguyên a.
EnumSet<Capability> result = a;
result.removeAll(b);
```

`result` và `a` là hai tham chiếu đến cùng một đối tượng. Gán một biến mới không tạo tập mới; A bị thay đổi.

Dùng:

```java
// Minh họa không sửa tập a.
EnumSet<Capability> result = EnumSet.copyOf(a);
result.removeAll(b);
```

Bản sao có cấu trúc thành viên riêng; thêm/xóa hằng ở bản sao không tự sửa tập gốc.

Một bộ hàm tiện ích có thể quy định rõ “trả kết quả mới, giữ đầu vào”:

```java
// Phương thức minh họa; cần import java.util.EnumSet.
static <E extends Enum<E>> EnumSet<E> difference(
        EnumSet<E> first,
        EnumSet<E> second) {
    EnumSet<E> result = EnumSet.copyOf(first);
    result.removeAll(second);
    return result;
}
```

Tham số kiểu `E` giữ hai đầu vào và kết quả cùng một kiểu enum. Không cần ép kiểu hoặc trộn các hằng enum không liên quan.

Với đầu vào là `EnumSet`, `copyOf` giữ được kiểu enum ngay cả khi tập rỗng. Không đồng nhất điều này với việc sao chép một collection rỗng thông thường không cung cấp đủ metadata kiểu enum.

## 7. Nhìn các phép toán qua vector bit

`EnumSet` dùng biểu diễn vector bit cho tập hằng enum. Với thứ tự bit khái niệm:

```text
Vị trí:     EXECUTE DELETE WRITE READ
A:             0      0     1     1
B:             0      1     1     0
A hợp B:       0      1     1     1
A giao B:      0      0     1     0
A trừ B:       0      0     0     1
```

Ý nghĩa:

- Hợp giữ vị trí có mặt ở ít nhất một đầu vào.
- Giao giữ vị trí cùng có mặt.
- Hiệu giữ vị trí có ở A và không có ở B.

Đây là cách giải thích vì sao các thao tác tập hợp rất phù hợp với biểu diễn của `EnumSet`. Người dùng vẫn gọi API tập hợp, không tự thao tác số bit nội bộ.

Không coi hình vẽ là một định dạng mã hóa bên ngoài hoặc tự lưu `ordinal` làm hợp đồng bền vững. Nếu kiểu enum thay đổi, các giả định dựa trên thứ tự hằng có thể không còn đúng.

Các tối ưu cụ thể phụ thuộc triển khai và cách đối số được biểu diễn. Không cần khẳng định mọi phép toán luôn là một lệnh máy hoặc đưa ra một hệ số hiệu năng cố định để dùng API đúng.

## 8. Tập rỗng, chính nó và giá trị boolean thay đổi

Một số quy tắc giúp kiểm tra kết quả:

| Biểu thức tập hợp | Kết quả |
| --- | --- |
| `A ∪ ∅` | A |
| `A ∩ ∅` | Tập rỗng |
| `A \ ∅` | A |
| `∅ \ A` | Tập rỗng |
| `A ∩ A` | A |
| `A \ A` | Tập rỗng |

Các phương thức tại chỗ vẫn tuân theo ý nghĩa này:

- `a.addAll(a)` không thêm thành viên mới.
- `a.retainAll(a)` không loại thành viên.
- `a.removeAll(a)` làm A rỗng.

Nếu A đã rỗng, thao tác làm rỗng không có thay đổi để báo về. Nếu thêm B vào một tập đã chứa mọi thành viên B, `addAll` trả về `false`.

Ví dụ:

```java
// Minh họa trong một phương thức.
EnumSet<Capability> working = EnumSet.of(Capability.READ);
EnumSet<Capability> extra = EnumSet.of(Capability.WRITE);

boolean firstChange = working.addAll(extra);
boolean secondChange = working.addAll(extra);
```

`firstChange` là `true`, `secondChange` là `false`; cả hai lần đều để lại một tập hợp lệ có `READ` và `WRITE`.

Không dùng giá trị trả về để thay cho kiểm tra tập kết quả rỗng hay không. Khi cần kiểm tra rỗng, gọi `isEmpty()` trên tập.

## 9. Chương trình đầy đủ

Lưu vào `EnumSetAlgebraDemo.java`:

```java
import java.util.EnumSet;

public class EnumSetAlgebraDemo {
    enum Capability {
        READ,
        WRITE,
        DELETE,
        EXECUTE
    }

    static <E extends Enum<E>> EnumSet<E> union(
            EnumSet<E> first, EnumSet<E> second) {
        EnumSet<E> result = EnumSet.copyOf(first);
        result.addAll(second);
        return result;
    }

    static <E extends Enum<E>> EnumSet<E> intersection(
            EnumSet<E> first, EnumSet<E> second) {
        EnumSet<E> result = EnumSet.copyOf(first);
        result.retainAll(second);
        return result;
    }

    static <E extends Enum<E>> EnumSet<E> difference(
            EnumSet<E> first, EnumSet<E> second) {
        EnumSet<E> result = EnumSet.copyOf(first);
        result.removeAll(second);
        return result;
    }

    public static void main(String[] args) {
        EnumSet<Capability> a =
                EnumSet.of(Capability.READ, Capability.WRITE);
        EnumSet<Capability> b =
                EnumSet.of(Capability.WRITE, Capability.DELETE);

        System.out.println("A=" + a);
        System.out.println("B=" + b);
        System.out.println("union=" + union(a, b));
        System.out.println("intersection=" + intersection(a, b));
        System.out.println("A-B=" + difference(a, b));
        System.out.println("B-A=" + difference(b, a));
        System.out.println("complementB=" + EnumSet.complementOf(b));

        EnumSet<Capability> symmetric = difference(a, b);
        symmetric.addAll(difference(b, a));
        System.out.println("symmetric=" + symmetric);

        System.out.println("A after=" + a);
        System.out.println("B after=" + b);

        EnumSet<Capability> working = EnumSet.copyOf(a);
        boolean firstChange = working.addAll(b);
        boolean secondChange = working.addAll(b);
        System.out.println("changed=" + firstChange + "/" + secondChange);

        EnumSet<Capability> empty =
                EnumSet.noneOf(Capability.class);
        System.out.println("emptyUnion=" + union(a, empty));
        System.out.println("emptyIntersection=" + intersection(a, empty));
        System.out.println("selfDifference=" + difference(a, a));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumSetAlgebraDemo.java
java EnumSetAlgebraDemo
```

Stdout chính xác:

```text
A=[READ, WRITE]
B=[WRITE, DELETE]
union=[READ, WRITE, DELETE]
intersection=[WRITE]
A-B=[READ]
B-A=[DELETE]
complementB=[READ, EXECUTE]
symmetric=[READ, DELETE]
A after=[READ, WRITE]
B after=[WRITE, DELETE]
changed=true/false
emptyUnion=[READ, WRITE]
emptyIntersection=[]
selfDifference=[]
```

Các điểm cần đối chiếu:

1. Hợp và giao giữ đúng những thành viên theo định nghĩa.
2. Hai chiều hiệu cho hai kết quả khác nhau.
3. Phần bù xét toàn bộ miền enum nên có thêm `EXECUTE` trong ví dụ.
4. Hiệu đối xứng không giữ phần tử chung `WRITE`.
5. A và B sau các lời gọi vẫn giữ nguyên vì các hàm tạo bản sao trước khi sửa.
6. Giá trị `boolean` báo thay đổi, không thay thế tập kết quả.
7. Tập rỗng và phép trừ chính nó hoạt động theo cùng quy tắc tập hợp.

Các kết quả được in theo thứ tự khai báo hằng enum, không theo thứ tự một phần tử được thêm từ đầu vào nào. Thứ tự đó giúp trình bày ổn định nhưng không thay đổi ngữ nghĩa thành viên của phép toán.

## 10. Khi dùng trong mã ứng dụng

Trước khi gọi phép toán, xác định rõ cần giữ nguyên hay sửa đầu vào.

Nếu phương thức chỉ tính một nhóm kết quả mới, sao chép trước thường làm hợp đồng dễ hiểu hơn. Nếu một thuật toán sở hữu riêng tập làm việc và chủ động tích lũy kết quả, thao tác tại chỗ có thể phù hợp.

Không công khai một tập thay đổi được rồi giả định bên nhận sẽ không sửa nó. Khi cần một ảnh chụp thành viên không cho sửa từ bên ngoài, có thể tạo bản sao và bọc bằng một giao diện không sửa đổi phù hợp. Chỉ bọc một tham chiếu đến tập gốc không đồng nghĩa tạo ảnh chụp độc lập.

Các phép toán trên nhiều tập cũng không tự tạo một giao dịch nguyên tử. Nếu các đầu vào được luồng khác thay đổi, phải có hợp đồng chia sẻ/đồng bộ riêng. Trong ví dụ học tập, các đầu vào được sở hữu và dùng tuần tự.

Các tập trong bài đều thuộc cùng kiểu enum và không chứa `null`. Không bỏ kiểm tra kiểu để đưa một enum khác vào chỉ vì tên hằng hoặc vị trí khai báo trông giống nhau.

## 11. Những lỗi thường gặp và tự luyện

Những lỗi cần tránh:

- Dùng `addAll` khi cần giao hoặc dùng `retainAll` khi muốn loại phần giao.
- Đổi nhầm chiều `A - B` thành `B - A`.
- Gán `result = a` rồi tưởng đã sao chép.
- Mong các phương thức bulk trả về một tập mới.
- Đọc `false` từ `retainAll` thành “không có giao”.
- Dùng phần bù thay cho phép hiệu mà quên miền enum.
- Coi các nhóm tên hằng giống nhau của hai enum khác nhau là cùng miền phần tử.

Bài tập:

1. Cho A chứa `READ, EXECUTE`, B chứa `READ, WRITE`. Dự đoán hợp, giao và cả hai chiều hiệu trước khi chạy.
2. Thay `EnumSet.copyOf(first)` bằng `first` trong một hàm tiện ích rồi quan sát tập đầu vào thay đổi. Giải thích bằng quan hệ tham chiếu.
3. Tạo trường hợp `retainAll` trả về `false` nhưng kết quả không rỗng.
4. Kiểm tra phép hợp với tập rỗng và hiệu của một tập với chính nó.
5. So sánh `difference(a, b)` với `complementOf(b)` khi miền enum có một hằng không thuộc cả A lẫn B.
6. Viết hàm hiệu đối xứng bằng hai phép hiệu và một phép hợp, giữ nguyên đầu vào.
7. Nếu một cấu hình cho phép bổ sung hằng enum mới, cần xét gì trước khi dùng phần bù để suy ra tập lựa chọn?

## Tài liệu đối chiếu

- [Java API — EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html): biểu diễn tập enum, sao chép và phần bù.
- [Java API — Set.addAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#addAll(java.util.Collection)): thêm các thành viên từ đối số.
- [Java API — Set.retainAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#retainAll(java.util.Collection)): giữ giao và ý nghĩa giá trị trả về.
- [Java API — Set.removeAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#removeAll(java.util.Collection)): loại các thành viên có trong đối số.
