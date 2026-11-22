# So sánh đối tượng bằng `IsSameObject` thay vì so giá trị tham chiếu JNI

## 1. Bài toán: cùng một đối tượng Java có thể có nhiều JNI reference

Khi mã Java gọi phương thức `native`, JVM chuyển đối tượng Java sang phía C/C++ dưới dạng một **JNI reference** như `jobject`, `jstring`, `jclass` hoặc `jarray`. Các giá trị này là *handle/reference do JVM quản lý*, không phải địa chỉ bộ nhớ ổn định của Java object để lập trình viên có thể so trực tiếp bằng các toán tử con trỏ C.

Giả sử Java truyền cùng một đối tượng vào hai vị trí tham số. JNI có thể cung cấp các handle khác nhau cùng trỏ tới một object. Ngoài ra, `NewLocalRef` hoặc `NewGlobalRef` còn có thể tạo reference mới tới object đã có. Vì thế, thao tác:

```c
/* SAI để khẳng định hai JNI reference trỏ tới cùng Java object. */
if (first == second) {
    /* Không bảo đảm là phép kiểm tra danh tính object. */
}
```

chỉ so sánh **biểu diễn của hai giá trị reference ở phía C**, điều mà JNI specification không cam kết là danh tính object. Một số JVM hoặc lần chạy có thể tình cờ cho kết quả đúng, nhưng chương trình sẽ phụ thuộc chi tiết implementation. Không được biến sự trùng nhau của các địa chỉ/handle quan sát được thành hợp đồng của JNI.

JNI cung cấp hàm chính thức:

```c
jboolean IsSameObject(JNIEnv *env, jobject ref1, jobject ref2);
```

Khi dùng JNI trong **C**, cú pháp gọi là:

```c
jboolean same = (*env)->IsSameObject(env, first, second);
```

Còn trong **C++**:

```cpp
jboolean same = env->IsSameObject(first, second);
```

`IsSameObject` kiểm tra xem hai reference hợp lệ có cùng trỏ tới **một Java object** hay không. Kết quả là `JNI_TRUE` hoặc `JNI_FALSE`. Không cần và không nên tự giải mã biểu diễn của `jobject`.

**Quy tắc lựa chọn:** muốn kiểm tra *cùng object trong heap Java* thì dùng `IsSameObject`; muốn kiểm tra *bằng nhau theo ý nghĩa ứng dụng* thì dùng `equals` hoặc quy tắc so sánh giá trị phù hợp. Đây là hai câu hỏi khác nhau.

## 2. Ba phép so sánh dễ bị nhầm

| Phép so sánh | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Java `a == b` với reference | Hai biến Java cùng trỏ tới một object hay không? | Hai `String` tạo riêng có thể chứa cùng nội dung nhưng `a == b` là `false` |
| Java `a.equals(b)` | Object `a` định nghĩa sự bằng nhau về **giá trị/ngữ nghĩa** thế nào? | Hai `new String("jni")` có `equals` bằng `true` |
| JNI `IsSameObject(env, a, b)` | Hai **JNI reference** trỏ tới cùng Java object hay không? | Local ref và global ref cùng trỏ tới một instance cho `JNI_TRUE` |
| C/C++ `a == b` trên hai JNI reference | Hai biểu diễn handle có so sánh bằng nhau trong code native hay không? | **Không phải phép kiểm tra danh tính object được JNI bảo đảm** |

Ví dụ Java:

```java
String a = new String("jni");
String b = new String("jni");

System.out.println(a == b);       // false: hai object khác nhau
System.out.println(a.equals(b));  // true: nội dung giống nhau
```

`IsSameObject(env, refA, refB)` tương ứng về **ngữ nghĩa danh tính** với Java `a == b`, *không phải* `a.equals(b)`. JNI không tự gọi `equals()`, không thực hiện so sánh nội dung String, mảng, record hay giá trị field.

Một vài cách khác cũng **không thay thế** `IsSameObject`:

- `System.identityHashCode(object)` trả về **hash dạng `int`**, không phải mã định danh duy nhất: hai object khác nhau có thể trùng hash (collision).
- `GetObjectClass` cho biết class của object; hai instance có thể cùng class nhưng không phải một object.
- `memcmp(&refA, &refB, sizeof(jobject))` chỉ so bytes biểu diễn handle trong bộ nhớ native; JNI không định nghĩa bytes đó là danh tính object.
- Ép `jobject` thành `void *` hoặc số nguyên rồi đưa vào map/set như một object ID ổn định là sai về mặt hợp đồng và còn gặp rủi ro khi reference hết hạn.

## 3. Chính xác `IsSameObject` trả về gì?

Theo JNI specification, `IsSameObject` trả `JNI_TRUE` nếu hai tham số cùng tham chiếu một Java object **hoặc cả hai đều là `NULL`**; các trường hợp khác trả `JNI_FALSE`.

| `ref1` | `ref2` | Kết quả |
| --- | --- | --- |
| Local ref A tới object X | Local ref B khác cũng tới X | `JNI_TRUE` |
| Local ref tới X | Global ref tới X | `JNI_TRUE` |
| Ref tới X | Ref tới Y khác X, dù `X.equals(Y)` là `true` | `JNI_FALSE` |
| `NULL` | `NULL` | `JNI_TRUE` |
| `NULL` | Ref hợp lệ tới một object còn sống | `JNI_FALSE` |

Ví dụ tối thiểu để phân biệt:

```c
jboolean sameObject =
        (*env)->IsSameObject(env, left, right);

if (sameObject == JNI_TRUE) {
    /* left và right cùng chỉ tới một object,
       hoặc cả hai đều NULL. */
}
```

**Hai lưu ý về điều kiện đầu vào:**

1. `IsSameObject` chỉ nên nhận JNI reference **còn hợp lệ** trong phạm vi/lifetime của chúng hoặc `NULL`. Nó không hợp pháp hóa reference đã được `DeleteLocalRef`/`DeleteGlobalRef`, reference từ thread khác dùng sai phạm vi hoặc giá trị tự ép từ địa chỉ tùy ý.
2. `IsSameObject(ref, NULL)` có thể dùng để kiểm tra NULL theo ngữ nghĩa JNI; với **weak global reference**, quy tắc còn có tác động đặc biệt khi object được GC thu hồi (phần 6). Với local/global reference mạnh và còn hợp lệ, `ref == NULL` là cách kiểm tra *giá trị null* thông thường; điều cần tránh là `ref1 == ref2` giữa **hai reference không null** để suy ra object identity.

## 4. Vì sao reference có thể khác nhau dù cùng trỏ tới một object?

JNI cố ý tách biệt **object Java** với **handle** mà mã native nắm giữ:

```text
                  Java heap
             ┌──────────────────┐
             │ Object X         │
             │  ("JNI example") │
             └──────────────────┘
                  ↑      ↑
                  │      │
     JNI local ref A      JNI global ref B
     (lời gọi hiện tại)   (giữ qua nhiều lời gọi)
                  │      │
               jobject jobject
```

Đường nối cùng hướng về Object X, song JVM có quyền biểu diễn hai reference bằng những giá trị handle khác nhau. Garbage collector có thể di chuyển object thực trong heap mà JNI reference vẫn dùng được vì JVM quản lý tầng gián tiếp cần thiết.

Ba loại reference quan trọng:

- **Local reference**: thường nhận từ tham số `native` hoặc hàm JNI như `NewLocalRef`/`FindClass`. Có phạm vi hợp lệ gắn với luồng và native frame; các local ref thông thường được tự động giải phóng khi native method return. Dùng `DeleteLocalRef` sớm khi tạo nhiều reference trong vòng lặp.
- **Global reference**: tạo bằng `NewGlobalRef` và phải dọn bằng `DeleteGlobalRef`. Nó giữ object còn được tham chiếu mạnh cho tới khi bị xóa, thích hợp nếu cần lưu qua nhiều native calls. Không được giữ local ref rồi sử dụng nó như global ref.
- **Weak global reference**: tạo bằng `NewWeakGlobalRef`, xóa bằng `DeleteWeakGlobalRef`. Nó không giữ object sống; sau khi GC thu hồi referent, weak ref trở nên có hiệu lực như `NULL`. Không được dùng một phép so sánh tại thời điểm trước như sự đảm bảo rằng object vẫn sống ở lần gọi sau.

`IsSameObject` thực hiện phép so sánh dựa trên **object mà reference đại diện**, độc lập việc handle được tạo qua local hay global, miễn reference còn hợp lệ. Nó **không kéo dài** lifetime của một local/global ref sau khi ref bị xóa, và không cung cấp một khóa định danh bền vững qua nhiều lần GC hoặc nhiều process.

## 5. Ví dụ Java 17+ và C JNI chạy được

Ví dụ này kiểm chứng bốn việc: (1) hai local ref tới cùng object được nhận diện đúng; (2) hai `String` có nội dung bằng nhau nhưng là hai object khác nhau; (3) local và global reference cùng trỏ một object; (4) `NULL` được xử lý đúng.

Môi trường minh họa: JDK 17+, một trình biên dịch C như GCC hoặc Clang trên **Linux**. Với Windows/macOS phải dùng lệnh build và thư viện động tương ứng nền tảng.

### 5.1. Tệp `NativeIdentity.java`

```java
public final class NativeIdentity {
    static {
        System.loadLibrary("identityjni");
    }

    private NativeIdentity() {
    }

    private static native boolean same(Object left, Object right);

    private static native boolean globalRoundTrip(Object value);

    public static void main(String[] args) {
        String first = new String("jni");
        String second = new String("jni");

        System.out.println("same reference: "
                + same(first, first));
        System.out.println("equal text, distinct objects: "
                + same(first, second));
        System.out.println("Java equals: "
                + first.equals(second));
        System.out.println("local and global: "
                + globalRoundTrip(first));
        System.out.println("both null: "
                + same(null, null));
        System.out.println("one null: "
                + same(first, null));
    }
}
```

`new String("jni")` tạo hai đối tượng String riêng biệt; hai object có nội dung `"jni"` bằng nhau. Cả hai native methods khai báo là `static` nên tham số ẩn tương ứng bên C là `jclass`, không phải `jobject this`.

### 5.2. Tệp `native_identity.c`

```c
#include <stddef.h>
#include "NativeIdentity.h"

JNIEXPORT jboolean JNICALL Java_NativeIdentity_same(
        JNIEnv *env, jclass cls, jobject left, jobject right) {
    (void)cls;
    return (*env)->IsSameObject(env, left, right);
}

JNIEXPORT jboolean JNICALL Java_NativeIdentity_globalRoundTrip(
        JNIEnv *env, jclass cls, jobject value) {
    (void)cls;

    /* Tạo global reference mới tới cùng Java object. */
    jobject global = (*env)->NewGlobalRef(env, value);

    /* Nếu value khác NULL mà cấp phát ref thất bại,
       JVM có thể đang có OutOfMemoryError chờ xử lý.
       Trả về để lỗi pending được truyền về Java. */
    if (value != NULL && global == NULL) {
        return JNI_FALSE;
    }

    /* So sánh object identity, không so hai giá trị jobject. */
    jboolean result = (*env)->IsSameObject(env, value, global);

    if (global != NULL) {
        (*env)->DeleteGlobalRef(env, global);
    }
    return result;
}
```

Đoạn `globalRoundTrip` quan trọng vì `global` là **một reference mới**. Chúng ta chỉ biết nó cùng chỉ tới một object nhờ `IsSameObject`; không được giả định `global == value`. Sau phép thử phải `DeleteGlobalRef` để không rò rỉ reference.

Chữ ký hàm JNI tương ứng được tạo tự động từ Java class bằng `javac -h`. Tên entry point trong code này phù hợp vì class nằm ở **default package** và hai tên native method không bị overload. Với tên package/phương thức khác, không nên tự đoán symbol: sử dụng header do `javac -h` tạo.

### 5.3. Biên dịch và chạy trên Linux

Đứng ở thư mục chứa hai tệp `NativeIdentity.java` và `native_identity.c`. Biến `JAVA_HOME` phải trỏ tới JDK chứa các header `jni.h`.

```bash
mkdir -p build

javac -h build -d build NativeIdentity.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild \
  native_identity.c -o libidentityjni.so

java -Djava.library.path=. -cp build NativeIdentity
```

Các lệnh trên lần lượt sinh `NativeIdentity.class`, header `build/NativeIdentity.h`, thư viện động `libidentityjni.so` và gọi chương trình Java. Tên logic `identityjni` được ánh xạ thành `libidentityjni.so` trên Linux.

**Stdout dự kiến:**

```text
same reference: true
equal text, distinct objects: false
Java equals: true
local and global: true
both null: true
one null: false
```

Kết quả không phụ thuộc hai giá trị `jobject` có tình cờ bằng nhau hay không. Nếu JVM/JDK mới yêu cầu cấp quyền native access cho code trên classpath, có thể thêm `--enable-native-access=ALL-UNNAMED` vào lệnh `java` theo hướng dẫn của phiên bản JDK đó; tùy chọn này không làm thay đổi ý nghĩa của `IsSameObject`.

### 5.4. Những điều ví dụ đã kiểm chứng

- `same(first, first)` là `true` vì cùng Java instance.
- `same(first, second)` là `false` dù `first.equals(second)` là `true`; **identity khác value equality**.
- `globalRoundTrip(first)` là `true` vì `NewGlobalRef` tạo một global ref tới chính object từ tham số.
- `same(null, null)` là `true` theo quy tắc JNI (tương tự Java `null == null`).
- `same(first, null)` là `false` vì một tham chiếu chỉ đến object còn tham chiếu kia là null.

## 6. Đặc biệt quan trọng: `jweak` và khoảng trống giữa kiểm tra với sử dụng

Một **weak global reference** (`jweak`) cho phép Java object bị GC thu hồi. JNI quy định có thể so sánh weak ref với `NULL`:

```c
jboolean cleared = (*env)->IsSameObject(env, weak, NULL);
```

Khi referent đã bị GC thu hồi, weak reference trở nên tương đương `NULL`, nên kết quả là `JNI_TRUE`. Tuy nhiên, có một lỗi race thường gặp:

```c
/* Không an toàn nếu sau phép kiểm tra này object chỉ còn weak ref. */
if ((*env)->IsSameObject(env, weak, NULL) == JNI_FALSE) {
    /* Một GC có thể chạy sau phép kiểm tra!
       Không được kết luận weak chắc chắn còn sống
       cho mọi JNI function call tiếp theo. */
}
```

**Mẫu đúng cho sử dụng kế tiếp:** tạo một **strong local reference** từ weak ref, rồi làm việc qua strong ref đó trong phạm vi còn hợp lệ.

```c
/* Fragment: weak là một jweak còn hợp lệ;
   candidate là local/global reference hợp lệ hoặc NULL. */
static jboolean matches_live_referent(
        JNIEnv *env, jweak weak, jobject candidate) {

    jobject strong = (*env)->NewLocalRef(env, weak);

    if (strong == NULL) {
        /* Referent có thể đã bị thu hồi.
           Nếu cấp phát reference thất bại, cũng phải
           kiểm tra ngoại lệ JNI đang pending. */
        return JNI_FALSE;
    }

    jboolean same =
            (*env)->IsSameObject(env, strong, candidate);

    (*env)->DeleteLocalRef(env, strong);
    return same;
}
```

Đây là **hàm trợ giúp minh họa**, chưa phải một chương trình Java/C độc lập. Nó trả `JNI_FALSE` khi không lấy được **referent còn sống**. Trường hợp pending `OutOfMemoryError` phải được xử lý/để lan truyền ở phía gọi; không được âm thầm coi mọi `NULL` từ `NewLocalRef` là “đã GC”. Khi tạo local ref thành công, strong ref giúp ngăn object bị thu hồi trong khoảng thời gian cần dùng. Sau đó `DeleteLocalRef` để giải phóng reference.

**Điểm tinh tế:** `IsSameObject(weak, NULL)` là một phép **quan sát trạng thái tại thời điểm gọi**, không phải cách “pin” referent. Nếu muốn *so sánh rồi tiếp tục sử dụng object*, cần chuyển weak sang strong reference trước; không tách hai thao tác bằng khoảng thời gian không được bảo vệ.

## 7. So sánh trong cache, callback và nhiều luồng

### 7.1. Muốn giữ object giữa hai lần gọi JNI: dùng global reference

Sai lầm phổ biến là ghi một `jobject` local vào biến `static` hoặc container native để dùng ở lần gọi sau:

```c
/* SAI: obj có thể là local ref hết hiệu lực sau khi return. */
static jobject cached;

static void unsafe_save(jobject obj) {
    cached = obj;
}
```

Cách đúng về **lifetime** là tạo global reference và giải phóng khi không còn dùng:

```c
/* Fragment: được gọi khi đang ở một native frame hợp lệ.
   Cần đồng bộ riêng nếu có nhiều thread dùng shared cache. */
jobject persistent = (*env)->NewGlobalRef(env, obj);

/* ... sử dụng persistent trong những JNI call về sau ... */

(*env)->DeleteGlobalRef(env, persistent);
```

Cần xử lý `NULL` do object đầu vào null hoặc hết bộ nhớ; không được dùng `persistent` nếu quá trình tạo global reference thất bại. Lưu global ref lâu sẽ giữ object sống và có thể gây leak, nên mỗi `NewGlobalRef` cần có lối cleanup phù hợp. Với global ref cache, hãy sử dụng `IsSameObject` khi cần biết tham số mới có phải chính object đã lưu hay không.

**Không dùng `jobject` như khóa hash ổn định** dựa vào bits của handle. Với số lượng reference nhỏ, có thể tìm tuyến tính bằng `IsSameObject`; nếu cần map hiệu năng cao, cân nhắc quản lý khóa ổn định ở lớp Java hoặc cấp ID riêng có lifecycle rõ ràng (không dùng identity hash làm ID duy nhất).

### 7.2. Một `JNIEnv *` chỉ dành cho luồng sở hữu

`JNIEnv *` là interface của JNI gắn với thread đang gọi. Không cache một `JNIEnv *` rồi đưa sang thread khác. Mã native chạy ở thread khác cần attach thread vào JVM đúng cách để nhận `JNIEnv *` của thread ấy và detach khi thích hợp. Global reference có thể được sử dụng qua các thread đã attach hợp lệ, nhưng trạng thái cache chung cần đồng bộ truy cập và không được xóa global ref trong khi thread khác đang dùng nó mà chưa có giao thức vòng đời an toàn.

### 7.3. Bằng nhau về nội dung cần gọi logic Java

Nếu yêu cầu nghiệp vụ là “hai object có cùng giá trị hay không?”, `IsSameObject` không giải quyết bài toán đó. Phía Java thường dùng:

```java
import java.util.Objects;

// Có ngữ nghĩa equals và xử lý hai tham số null.
boolean equalValues = Objects.equals(left, right);

// Có ngữ nghĩa identity.
boolean sameInstance = left == right;
```

Đây là **mảnh Java minh họa**, giả định `left` và `right` là hai biến đã có. Nếu so sánh nội dung thật sự từ native, có thể gọi `equals(Object)` qua `GetMethodID` + `CallBooleanMethod` và xử lý exception, hoặc tốt hơn là cho Java tính `Objects.equals` rồi chuyển kết quả xuống JNI. Bản thân `IsSameObject` không thực thi phương thức Java nào.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `a == b` với hai `jobject` | So biểu diễn JNI handles, không so Java object identity | `(*env)->IsSameObject(env, a, b)` |
| Cho rằng `IsSameObject` gọi `equals()` | So identity, không so ngữ nghĩa của object | Dùng `equals` hoặc `Objects.equals` nếu cần so giá trị |
| So `System.identityHashCode(a) == System.identityHashCode(b)` | Hash có thể collision | Dùng identity trực tiếp |
| Lưu local `jobject` qua nhiều lần native call | Local ref hết hạn khi native frame kết thúc | Dùng `NewGlobalRef`/`DeleteGlobalRef` |
| Lấy `IsSameObject(weak, NULL)` làm bằng chứng weak luôn còn sống | GC có thể thu hồi ngay sau khi kiểm tra | `NewLocalRef` rồi dùng strong ref |
| Tiếp tục dùng reference đã `DeleteLocalRef` | Invalid reference, hành vi không được định nghĩa cho tác vụ JNI tiếp theo | Đảm bảo lifetime, bỏ mọi use sau delete |
| Không xóa global ref khi cache hết hạn | Giữ object sống, gây leak | Hủy cache theo lifecycle và gọi `DeleteGlobalRef` |
| Cache `JNIEnv *` để dùng từ thread khác | `JNIEnv *` gắn với thread | Attach thread và lấy `JNIEnv *` hợp lệ |
| Ngầm tin hai class giống nội dung là một object | Class/instance identity vẫn phụ thuộc object và class loader | Xác định đúng instance; dùng `IsSameObject` cho object identity |

### Khi kết quả không như dự kiến

1. **Kiểm tra có thật là cùng instance Java?** Hai lần `new` tạo hai instance; `String` hoặc boxed type có thể khiến cảm giác “cùng nội dung” bị nhầm là “cùng object”. Đừng dựa vào tình cờ của String interning hay cache wrapper.
2. **Kiểm tra tham chiếu JNI còn hợp lệ?** Local ref có bị giữ ra ngoài native frame, bị xóa sớm hoặc dùng sai thread? Global ref đã bị `DeleteGlobalRef` chưa?
3. **Kiểm tra null/weak reference.** Cả hai null là `JNI_TRUE`; weak ref đã bị GC có thể được xem là null. Nếu sắp dùng weak, promote lên strong local/global trước.
4. **Kiểm tra có phải câu hỏi về `equals`?** Hai object khác nhau hoàn toàn có thể bằng nhau về giá trị.
5. **Khi debug native**, có thể dùng JNI Check mode (ví dụ `-Xcheck:jni` trên HotSpot hỗ trợ) để giúp phát hiện nhiều lỗi dùng reference/JNI API. Công cụ này hỗ trợ chẩn đoán, không biến việc so `jobject` bằng `==` thành phép kiểm tra identity hợp lệ.

## 9. Tự kiểm tra

**Câu 1.** `localA` và `globalB` đều trỏ đến Java object X nhưng các giá trị handle khác nhau. Phép nào đúng để biết chúng cùng X?  
**Đáp án:** `(*env)->IsSameObject(env, localA, globalB)`. Nếu cả hai reference hợp lệ và cùng X, kết quả là `JNI_TRUE`.

**Câu 2.** `new String("abc")` và `new String("abc")` có `equals` bằng `true`. `IsSameObject` của hai reference tới chúng trả gì?  
**Đáp án:** `JNI_FALSE`, vì đây là hai object riêng biệt.

**Câu 3.** Gọi `IsSameObject(env, NULL, NULL)` trả về gì?  
**Đáp án:** `JNI_TRUE`. JNI quy định rõ trường hợp cả hai đều null.

**Câu 4.** Một `jweak` vừa cho `IsSameObject(env, weak, NULL) == JNI_FALSE`. Ta có thể yên tâm dùng nó về sau không?  
**Đáp án:** Không. GC có thể chạy giữa hai thao tác. Tạo strong local reference bằng `NewLocalRef`, kiểm tra kết quả và sử dụng reference mạnh đó trong thời gian cần thiết.

**Câu 5.** Native code cần giữ object Java lâu hơn một lần gọi. Có thể gán tham số `jobject` vào biến static C rồi so ở lần sau không?  
**Đáp án:** Không, vì tham số thường là local ref. Phải tạo global ref (hoặc thiết kế một phương án lưu ở Java), quản lý đồng bộ nếu nhiều thread và dọn reference khi không dùng nữa.

**Câu 6.** `IsSameObject` có đủ để xác định hai `Person` có cùng `id` không?  
**Đáp án:** Không. Nếu quy tắc ứng dụng xem hai `Person` có cùng `id` là bằng nhau, hãy viết/áp dụng `equals` hoặc so sánh `id` phù hợp. `IsSameObject` chỉ trả lời chúng có phải một instance duy nhất hay không.

## 10. Ghi nhớ

- `jobject` là **JNI reference** do JVM quản lý; biểu diễn của handle không phải một Java object ID ổn định.
- So sánh **danh tính object** bằng `IsSameObject`. Trong C: `(*env)->IsSameObject(env, a, b)`; trong C++: `env->IsSameObject(a, b)`.
- Kết quả `JNI_TRUE` khi hai reference cùng trỏ một object **hoặc đều là `NULL`**.
- **Identity ≠ equality về giá trị:** `IsSameObject` tương ứng với Java reference `==`, không tương ứng `equals`.
- Tôn trọng **lifetime của local/global/weak references**: giữ object qua nhiều lời gọi bằng `NewGlobalRef`, cleanup bằng `DeleteGlobalRef`; với `jweak`, dùng `NewLocalRef` trước khi tiếp tục thao tác.
- Không dựa vào `jobject == jobject`, cast sang địa chỉ/số, `memcmp` hoặc `identityHashCode` để khẳng định hai JNI references cùng trỏ một Java object.

### Tài liệu chính thức

- [Oracle — JNI Functions: IsSameObject, NewGlobalRef, NewLocalRef, Weak Global References (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): chữ ký hàm, quy tắc null và vòng đời reference.
- [Oracle — JNI Design Overview: Referencing Java Objects (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): sự khác nhau giữa local/global references và mô hình xử lý object của JVM.
- [Oracle — JNI Functions (Java SE 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html): quy tắc `IsSameObject` và weak global references trên phiên bản tài liệu hiện đại.
