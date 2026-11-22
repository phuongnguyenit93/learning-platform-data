# Sao chép nông và chia sẻ các mảng con — Java 17+

## 1. Bản chất

`int[][]` trong Java là **mảng ngoài chứa các tham chiếu tới mảng con `int[]`**. Vì vậy **sao chép mảng ngoài không đồng nghĩa sao chép các hàng**.

~~~java
int[][] a = {{1, 2}, {3, 4, 5}};
~~~

Ở đây `a.length == 2`, `a[0].length == 2`, `a[1].length == 3`. Mỗi hàng là một đối tượng mảng riêng. Một **tham chiếu hàng** có thể được lưu ở nhiều vị trí, thậm chí trong nhiều mảng ngoài khác nhau.

~~~text
a (mảng ngoài) ---> [tham chiếu 0 | tham chiếu 1]
                          |               |
                          v               v
                      [1, 2]         [3, 4, 5]
                       int[]             int[]
~~~

**Shallow copy — sao chép nông:** chỉ tạo bản sao của **một tầng mảng**, còn các phần tử tham chiếu ở tầng ấy vẫn trỏ đến các đối tượng cũ.

## 2. So sánh các cách sao chép

| Thao tác với `int[][] a` | Mảng ngoài mới? | Các hàng `int[]` mới? |
|---|---|---|
| `int[][] b = a;` | Không | Không |
| `int[][] b = a.clone();` | **Có** | **Không** |
| `Arrays.copyOf(a, a.length)` | **Có** | **Không** |
| `System.arraycopy(a, 0, b, 0, a.length)` với `b` là mảng ngoài mới | Đích có mảng ngoài riêng | **Không** |
| Tạo mảng ngoài mới rồi `clone()` từng hàng | **Có** | **Có**, với hàng khác null |

Gán `b = a` không tạo bản sao: `a == b` là `true`. Ngược lại, `a.clone()` tạo mảng ngoài khác (`a == b` là `false`), nhưng thường `a[0] == b[0]` vẫn là `true`.

## 3. `clone()` tạo mảng ngoài mới, nhưng chia sẻ hàng

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] copy = original.clone();

copy[0][0] = 9;
System.out.println(java.util.Arrays.deepToString(original));
System.out.println(original == copy);
System.out.println(original[0] == copy[0]);
~~~

**Exact expected stdout:**

~~~text
[[9, 2], [3, 4]]
false
true
~~~

`copy[0][0] = 9` sửa **mảng con chung**. Cả hai mảng ngoài đều quan sát được giá trị mới.

Nhưng thay một **tham chiếu hàng** chỉ sửa mảng ngoài đang giữ nó:

~~~java
copy[1] = new int[]{8};
System.out.println(java.util.Arrays.deepToString(original));
System.out.println(java.util.Arrays.deepToString(copy));
~~~

**Exact expected stdout (tiếp theo):**

~~~text
[[9, 2], [3, 4]]
[[9, 2], [8]]
~~~

Phân biệt: `copy[row][col] = value` sửa **phần tử thuộc hàng**; `copy[row] = new int[]{...}` sửa **ô tham chiếu ở mảng ngoài**.

## 4. `Arrays.copyOf` và `System.arraycopy` cũng là sao chép nông ở tầng ngoài

~~~java
int[][] source = {{1, 2}, {3}};
int[][] copied = java.util.Arrays.copyOf(source, source.length);
int[][] target = new int[source.length][];
System.arraycopy(source, 0, target, 0, source.length);

System.out.println(source == copied);
System.out.println(source[0] == copied[0]);
System.out.println(source[0] == target[0]);
~~~

**Exact expected stdout:**

~~~text
false
true
true
~~~

Vì phần tử của `int[][]` là tham chiếu tới `int[]`, sao chép phần tử mảng ngoài chỉ sao chép **giá trị tham chiếu**, không tự gọi `clone()` trên các hàng.

Nếu `Arrays.copyOf(source, source.length + 1)`, ô hàng mới được thêm mặc định là `null`, không phải `new int[0]`.

## 5. Sao chép độc lập từng hàng `int[]`

Khi muốn sửa bản sao **không ảnh hưởng dữ liệu `int` trong mảng gốc**, cần tạo mảng ngoài và từng mảng con riêng:

~~~java
static int[][] detachRows(int[][] source) {
    if (source == null) return null;

    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = source[i] == null ? null : source[i].clone();
    }
    return copy;
}
~~~

- Mỗi hàng không null được `clone()` thành `int[]` mới.
- Hàng rỗng vẫn là một `int[]` dài 0 **mới**.
- Hàng null tiếp tục là null, không gọi `.clone()` lên null.
- Mỗi hàng giữ độ dài riêng, nên cách này dùng được với **mảng răng cưa** (*jagged array*).

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = detachRows(a);
b[0][0] = 99;

System.out.println(java.util.Arrays.deepToString(a));
System.out.println(java.util.Arrays.deepToString(b));
~~~

**Exact expected stdout:**

~~~text
[[1, 2], [3]]
[[99, 2], [3]]
~~~

Với **`int[][]`**, cách này đủ để tách biệt các giá trị nguyên thủy. Với mảng chứa đối tượng có thể thay đổi trạng thái, sao chép từng hàng vẫn có thể chưa đủ.

## 6. Hai hàng có thể cùng tham chiếu một mảng con

~~~java
int[] shared = {1, 2};
int[][] a = {shared, shared};

a[0][0] = 9;
System.out.println(java.util.Arrays.deepToString(a));
System.out.println(a[0] == a[1]);
~~~

**Exact expected stdout:**

~~~text
[[9, 2], [9, 2]]
true
~~~

Đây là **chia sẻ ngay bên trong cùng một mảng ngoài**. Khi dùng `detachRows(a)`, mỗi vị trí sẽ tạo một hàng mới riêng, tức **phá quan hệ cùng tham chiếu** dù giá trị ở mỗi hàng vẫn được sao chép đúng.

Nếu bài toán cần một bản sao có các hàng độc lập với nguồn **nhưng vẫn giữ quan hệ alias giữa các vị trí**, cần thuật toán khác (ví dụ ánh xạ identity từ hàng gốc sang hàng đã sao chép). Không mặc định mọi “deep copy” đều bảo toàn cấu trúc chia sẻ đối tượng.

## 7. Kiểu đối tượng mutable: clone hàng vẫn chia sẻ phần tử

~~~java
StringBuilder[][] a = {
    {new StringBuilder("A")}
};
StringBuilder[][] b = {a[0].clone()};

b[0][0].append("!");
System.out.println(a[0][0]); // A!
~~~

Mặc dù `a[0] != b[0]`, hai ô `a[0][0]` và `b[0][0]` vẫn cùng tham chiếu đối tượng `StringBuilder`, nên `append` làm bản gốc thay đổi.

Ngược lại, `b[0][0] = new StringBuilder("B")` chỉ thay tham chiếu tại **ô của hàng mới**, không đổi `a[0][0]`.

| Kiểu dữ liệu | Muốn tách biệt trạng thái, cần sao chép đến đâu? |
|---|---|
| `int[][]` | Mảng ngoài + từng hàng `int[]` |
| `String[][]` | Mảng ngoài + từng hàng thường đủ, vì `String` bất biến |
| `StringBuilder[][]` | Mảng ngoài + từng hàng + **từng `StringBuilder` mutable** |
| `int[][][]` | Phải xét cả **ba tầng mảng** |

`clone()` không phải lệnh “sao chép sâu tất cả các object bên trong”.

## 8. So sánh identity và nội dung

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = detachRows(a);

System.out.println(a == b);
System.out.println(java.util.Arrays.equals(a, b));
System.out.println(java.util.Arrays.deepEquals(a, b));
System.out.println(java.util.Arrays.deepToString(b));
~~~

**Exact expected stdout:**

~~~text
false
false
true
[[1, 2], [3]]
~~~

- `==` so **cùng object mảng ngoài** hay không.
- `Arrays.equals(a,b)` so **phần tử tầng ngoài**; với `int[][]`, các phần tử là tham chiếu `int[]`, nên hai hàng mới khác identity thì không bằng nhau theo cách này.
- `Arrays.deepEquals(a,b)` so sánh **nội dung lồng nhau**.
- `Arrays.deepToString(a)` in nội dung các hàng dễ đọc.

**Nội dung bằng nhau không chứng minh hai cấu trúc độc lập**; phải xét tham chiếu chia sẻ theo từng tầng.

## 9. Chương trình Java 17 hoàn chỉnh

Lưu tên **`ShallowArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class ShallowArrayDemo {
    private ShallowArrayDemo() {}

    static int[][] detachRows(int[][] source) {
        if (source == null) return null;
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null ? null : source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3, 4, 5}};
        int[][] alias = source;
        int[][] shallow = source.clone();
        int[][] copied = Arrays.copyOf(source, source.length);
        int[][] arrayCopied = new int[source.length][];
        System.arraycopy(source, 0, arrayCopied, 0, source.length);

        System.out.println("alias outer=" + (source == alias));
        System.out.println("clone outer=" + (source == shallow));
        System.out.println("clone row0=" + (source[0] == shallow[0]));
        System.out.println("copyOf row1=" + (source[1] == copied[1]));
        System.out.println("arraycopy row0=" + (source[0] == arrayCopied[0]));

        shallow[0][0] = 9;
        System.out.println("source after shallow=" + Arrays.deepToString(source));

        copied[1] = new int[]{8};
        System.out.println("source row1=" + Arrays.toString(source[1]));
        System.out.println("copied row1=" + Arrays.toString(copied[1]));

        arrayCopied[1][1] = 7;
        System.out.println("source after arraycopy="
                + Arrays.deepToString(source));

        int[][] independent = detachRows(source);
        independent[0][0] = 100;
        System.out.println("original=" + Arrays.deepToString(source));
        System.out.println("independent=" + Arrays.deepToString(independent));
        System.out.println("independent shares row0="
                + (source[0] == independent[0]));
        System.out.println("deep equals changed="
                + Arrays.deepEquals(source, independent));
        System.out.println("deep equals fresh="
                + Arrays.deepEquals(source, detachRows(source)));

        int[][] ragged = {{4}, null, {}};
        int[][] raggedCopy = detachRows(ragged);
        System.out.println("ragged copy=" + Arrays.deepToString(raggedCopy));
        System.out.println("null preserved=" + (raggedCopy[1] == null));
        System.out.println("row detached=" + (ragged[0] != raggedCopy[0]));

        int[] same = {1, 2};
        int[][] repeated = {same, same};
        int[][] repeatedShallow = repeated.clone();
        int[][] repeatedDetached = detachRows(repeated);
        System.out.println("same source rows=" + (repeated[0] == repeated[1]));
        System.out.println("same shallow rows="
                + (repeatedShallow[0] == repeatedShallow[1]));
        System.out.println("same detached rows="
                + (repeatedDetached[0] == repeatedDetached[1]));

        repeated[0][0] = 6;
        System.out.println("repeated=" + Arrays.deepToString(repeated));
        System.out.println("repeated detached="
                + Arrays.deepToString(repeatedDetached));

        StringBuilder[][] objects = {{new StringBuilder("A")}};
        StringBuilder[][] rowCopy = {objects[0].clone()};
        rowCopy[0][0].append("!");
        System.out.println("mutable original=" + objects[0][0]);
        rowCopy[0][0] = new StringBuilder("B");
        System.out.println("mutable original after replace=" + objects[0][0]);
        System.out.println("mutable copy=" + rowCopy[0][0]);

        int[][][] cube = {{{1}}};
        int[][][] cubeCopy = cube.clone();
        System.out.println("3d level2 shared=" + (cube[0] == cubeCopy[0]));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ShallowArrayDemo.java
java -cp . ShallowArrayDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShallowArrayDemo.java
java -cp . ShallowArrayDemo
~~~

### Exact expected stdout

~~~text
alias outer=true
clone outer=false
clone row0=true
copyOf row1=true
arraycopy row0=true
source after shallow=[[9, 2], [3, 4, 5]]
source row1=[3, 4, 5]
copied row1=[8]
source after arraycopy=[[9, 2], [3, 7, 5]]
original=[[9, 2], [3, 7, 5]]
independent=[[100, 2], [3, 7, 5]]
independent shares row0=false
deep equals changed=false
deep equals fresh=true
ragged copy=[[4], null, []]
null preserved=true
row detached=true
same source rows=true
same shallow rows=true
same detached rows=false
repeated=[[6, 2], [6, 2]]
repeated detached=[[1, 2], [1, 2]]
mutable original=A!
mutable original after replace=A!
mutable copy=B
3d level2 shared=true
~~~

**Giải thích:** `clone()`, `Arrays.copyOf` và `System.arraycopy` trên `int[][]` vẫn chia sẻ hàng; `detachRows` tạo hàng `int[]` mới. Thay phần tử của hàng chia sẻ tác động bản gốc, còn thay cả tham chiếu hàng trong mảng ngoài riêng thì không. Với `StringBuilder[][]`, sao chép hàng không sao chép các object mutable.

## 10. Các lỗi thường gặp

| Sai lầm | Vì sao sai? | Sửa |
|---|---|---|
| `b = a` là bản sao | Chỉ thêm tên tham chiếu | Dùng clone hoặc sao chép hàng tùy nhu cầu |
| `a.clone()` là deep copy | Chỉ sao chép mảng ngoài | Clone từng hàng `int[]` |
| `Arrays.copyOf(a, a.length)` sao chép mọi `int[]` | Chỉ sao chép các tham chiếu hàng | Tạo mảng con mới |
| `System.arraycopy` tự clone các object con | Chỉ sao chép phần tử của mảng nguồn | Sao chép sâu theo dữ liệu |
| `b[0][0]` và `b[0]` là cùng loại thao tác | Một lệnh sửa ô, một lệnh thay hàng | Xác định đúng tầng tham chiếu |
| `source[i].clone()` khi hàng null | Ném `NullPointerException` | Kiểm tra null trước |
| `Arrays.equals` đủ để so ma trận theo giá trị | Nó so phần tử tầng ngoài | Dùng `Arrays.deepEquals` |
| Chỉ kiểm tra `a != b` để khẳng định độc lập | Các hàng vẫn có thể chung | So identity từng cấp |
| Clone hàng `StringBuilder[]` sẽ sao chép từng StringBuilder | Các object vẫn dùng chung | Tạo object mới cho từng phần tử mutable |
| Hai hàng nguồn dùng chung một object nhưng bản sao hàng tự giữ alias | Clone từng hàng làm tách alias | Nếu cần giữ alias nội bộ, dùng ánh xạ identity |

## 11. Bài tập có đáp án

**A — Dự đoán kết quả:**

~~~java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 7;
b[1] = new int[]{8};
System.out.println(Arrays.deepToString(a));
System.out.println(Arrays.deepToString(b));
~~~

**Đáp án:**

~~~text
[[7], [2]]
[[7], [8]]
~~~

**B — Vì sao `a == b` false nhưng sửa hàng vẫn thấy ở `a`?** Vì sao chép nông tạo mảng ngoài mới, còn `a[i] == b[i]` vẫn có thể true.

**C — Sao chép an toàn mảng răng cưa có hàng null:** dùng `detachRows` ở mục 5; `{{1}, null, {}}` được sao chép thành cấu trúc nội dung `[[1], null, []]` với các hàng không null độc lập.

**D — Muốn hai hàng cùng tham chiếu sau khi sao chép?** Không dùng trực tiếp hàm clone từng hàng độc lập; cần ánh xạ hàng gốc → hàng sao chép để tái sử dụng cùng hàng mới tại các vị trí tương ứng.

**E — Với `StringBuilder[][]` sao chép từng hàng đã đủ chưa?** Chưa nếu yêu cầu không chia sẻ trạng thái object. Cần tạo bản sao `StringBuilder` (hoặc object mutable tương ứng) trong từng ô.

## 12. Checklist và kết luận

- [ ] Hiểu `int[][]` chứa **tham chiếu hàng**.
- [ ] Phân biệt phép gán tham chiếu với bản sao nông.
- [ ] Biết `clone()`, `Arrays.copyOf`, `System.arraycopy` ở tầng ngoài vẫn chia sẻ mảng con.
- [ ] Hiểu `b[row][col] = x` khác `b[row] = new int[]{...}`.
- [ ] Sao chép được các hàng `int[]` độc lập, kể cả hàng rỗng và null.
- [ ] Nhận ra trường hợp nhiều hàng trỏ tới cùng một đối tượng `int[]`.
- [ ] Phân biệt mảng con và object mutable nằm trong phần tử mảng con.
- [ ] Dùng `Arrays.deepEquals` và `Arrays.deepToString` đúng mục đích.
- [ ] Chạy `ShallowArrayDemo.java` bằng Java 17+, đối chiếu stdout.

**Kết luận:** Sao chép nông của mảng nhiều chiều trong Java tạo **mảng ngoài mới nhưng vẫn chia sẻ các mảng con**. Thay nội dung hàng chung ảnh hưởng mọi tham chiếu tới hàng đó; thay tham chiếu hàng trong một mảng ngoài riêng thì không. Với `int[][]`, muốn độc lập dữ liệu hãy sao chép **cả mảng ngoài và từng `int[]` con**.