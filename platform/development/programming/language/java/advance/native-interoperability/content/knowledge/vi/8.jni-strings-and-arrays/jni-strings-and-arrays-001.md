# UTF-16 của Java và Modified UTF-8 của JNI khác UTF-8 thông thường

> **Phạm vi:** Java Advance → Native Interoperability → Chuỗi và mảng JNI. Mục tiêu là hiểu chính xác dữ liệu ký tự nào đi qua ranh giới Java–native, khi nào số lượng ký tự khác số byte và vì sao chuỗi nhận qua `GetStringUTFChars` không thể mặc nhiên dùng như UTF-8 chuẩn của file, mạng hoặc thư viện C/C++.

## 1. Ba khái niệm không được đánh đồng

**Unicode code point** là giá trị ký tự trừu tượng, ví dụ `U+0041` (A), `U+00E9` (é), `U+1F600` (😀). **UTF-16** và **UTF-8** là những cách mã hóa code point. JNI còn có **Modified UTF-8 (MUTF-8)**, một biến thể cố ý khác UTF-8 thông thường.

Trong Java, `String` được quan sát qua chuỗi các **UTF-16 code unit 16-bit**. `String.length()` đếm code unit; `charAt(i)` trả về một code unit; `codePointCount(...)` đếm code point theo quy tắc cặp surrogate. Một ký tự ngoài Basic Multilingual Plane (BMP), chẳng hạn 😀, cần **hai code unit** trong UTF-16 (một high surrogate và một low surrogate). Vì vậy:

```java
String smile = new String(Character.toChars(0x1F600));
System.out.println(smile.length());                   // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, 2));        // 1 code point
```

Đây là đoạn Java minh họa; một chương trình chạy đầy đủ nằm ở mục 4.

Không nên suy ra mọi `String` trong JVM đều chiếm `2 * length()` byte trên heap. Các JVM hiện đại có thể dùng **compact strings** hoặc biểu diễn nội bộ khác; hợp đồng API Java/JNI vẫn dùng mô hình UTF-16 code unit khi truy cập bằng `char`/`jchar`.

Ba dạng cần phân biệt:

| Dạng | Đơn vị quan sát | Điểm quan trọng | API liên quan |
|---|---|---|---|
| **UTF-16 (Java/JNI)** | Code unit 16-bit (cặp surrogate cho code point ngoài BMP) | Cho phép code unit `U+0000`, không có khái niệm byte kết thúc C | `String.length`, `charAt`, `GetStringChars`, `GetStringRegion`, `NewString` |
| **UTF-8 chuẩn** | Dãy byte 1–4 byte/code point hợp lệ | `U+0000` → `00`; 😀 → một dãy **4 byte**; dùng cho file, network, JSON, API text | `getBytes(StandardCharsets.UTF_8)`, `new String(bytes, UTF_8)`, `CharsetDecoder` |
| **JNI Modified UTF-8** | Dãy byte, mã hóa từng UTF-16 code unit thành 1–3 byte | `U+0000` → `C0 80`; 😀 → **hai nhóm 3 byte**; dùng bởi các API JNI có hậu tố `UTF` | `GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFRegion`, `NewStringUTF` |

**Điểm chốt:** Hậu tố `UTF` trong `GetStringUTFChars` **không** có nghĩa là UTF-8 chuẩn. JNI Specification định nghĩa đó là **modified UTF-8**.

## 2. Cơ chế byte: MUTF-8 khác UTF-8 chuẩn ở đâu?

MUTF-8 của JNI mã hóa các UTF-16 code unit:

- `U+0001` đến `U+007F` → **1 byte**, cùng biểu diễn với UTF-8 chuẩn (ví dụ A → `41`).
- `U+0000` → **2 byte `C0 80`** thay vì `00`. Điều này tránh có byte NUL bên trong phần payload ký tự.
- `U+0080` đến `U+07FF` → **2 byte**, thường giống UTF-8 chuẩn (é → `C3 A9`).
- `U+0800` đến `U+FFFF` → **3 byte cho mỗi UTF-16 code unit**. Với code point BMP hợp lệ không phải surrogate, ba byte thường trùng UTF-8 chuẩn.
- Với code point **ngoài BMP**, Java có *hai* surrogate code unit. MUTF-8 mã hóa mỗi surrogate thành 3 byte, tổng cộng **6 byte**. UTF-8 chuẩn mã hóa trực tiếp code point đó thành **4 byte**.

Bảng byte cụ thể (hex viết theo thứ tự truyền):

| Nội dung | UTF-16 code unit | UTF-8 chuẩn | JNI Modified UTF-8 |
|---|---|---|---|
| `A` (U+0041) | `0041` | `41` | `41` |
| `NUL` (U+0000) | `0000` | `00` | `C0 80` |
| `é` (U+00E9) | `00E9` | `C3 A9` | `C3 A9` |
| `😀` (U+1F600) | `D83D DE00` | `F0 9F 98 80` | `ED A0 BD ED B8 80` |

Vì sao 😀 trở thành `ED A0 BD ED B8 80`?

1. Code point `U+1F600` chuyển thành cặp UTF-16 `D83D` (high surrogate) + `DE00` (low surrogate).
2. MUTF-8 mã hóa `D83D` thành `ED A0 BD`.
3. MUTF-8 mã hóa `DE00` thành `ED B8 80`.
4. Ghép theo thứ tự thành sáu byte: `ED A0 BD ED B8 80`.

Trong UTF-8 chuẩn, `ED A0 BD` biểu diễn một **surrogate code point**, vốn không được chấp nhận trong Unicode scalar values; `C0 80` cũng là dạng **overlong encoding** không hợp lệ cho U+0000. Bởi vậy một bộ giải mã UTF-8 **nghiêm ngặt** phải bác bỏ những dãy này. Không coi MUTF-8 là chuỗi UTF-8 chuẩn chỉ vì chữ "UTF-8" xuất hiện trong tên API.

### Vì sao MUTF-8 tồn tại?

C truyền thống sử dụng chuỗi byte kết thúc bởi `'\0'` (byte `00`). Nếu nội dung Java có U+0000 được gửi dưới dạng UTF-8 chuẩn, hàm C dựa trên `strlen` sẽ xem `00` là điểm kết thúc, làm **cắt ngắn** phần dữ liệu sau nó. MUTF-8 mã hóa U+0000 thành `C0 80` để tránh NUL nằm trong payload. Khi API cần chuỗi C kết thúc NUL (như `NewStringUTF`), caller vẫn phải chuẩn bị byte `00` **ở cuối buffer**.

**Lưu ý quan trọng:** Tài liệu JNI không bảo đảm mọi buffer lấy từ `GetStringUTFChars` hoặc `GetStringUTFRegion` đều NUL-terminated. Vì vậy, dù MUTF-8 tránh NUL trong payload, code native đúng vẫn dùng **độ dài tường minh**, và chỉ tự thêm byte `00` khi chính hợp đồng API yêu cầu C string kết thúc NUL.

## 3. Một chuỗi, ba phép đếm khác nhau

Xét chuỗi:

```java
String sample = "A" + '\0' + "\u00E9"
        + new String(Character.toChars(0x1F600));
```

Trong đó có **4 code point**: A, NUL, é và 😀. Nhưng số lượng theo từng biểu diễn là:

```text
Unicode code points (4) : U+0041 | U+0000 | U+00E9 | U+1F600

UTF-16 code units (5)  : 0041 | 0000 | 00E9 | D83D | DE00

UTF-8 chuẩn (8 byte)   : 41 | 00 | C3 A9 | F0 9F 98 80

JNI MUTF-8 (11 byte)   : 41 | C0 80 | C3 A9 | ED A0 BD ED B8 80
```

Do đó:

- `sample.length() == 5`, vì `String.length()` đếm UTF-16 code unit.
- `sample.codePointCount(0, sample.length()) == 4`.
- `sample.getBytes(StandardCharsets.UTF_8).length == 8`, vì UTF-8 chuẩn mã hóa trực tiếp các code point hợp lệ.
- Kích thước phần **MUTF-8 payload** là **11 byte**; không tính byte NUL kết thúc C hay byte framing của giao thức khác.

Không thể thay thế `GetStringLength` bằng `GetStringUTFLength` hoặc ngược lại. Một bên đo code unit; bên kia đo byte của **MUTF-8**, không phải UTF-8 chuẩn. Không thể dùng số code point để cấp phát byte buffer nếu chưa tính cách mã hóa.

## 4. Thực hành Java 17+: nhìn thấy byte trước khi viết JNI

Ta có thể tái tạo payload MUTF-8 bằng `DataOutputStream.writeUTF` để học cách mã hóa. API này viết **hai byte độ dài phía trước** MUTF-8, trong khi các JNI string APIs **không** dùng hai byte prefix đó. Ví dụ tách prefix ra để so sánh. `writeUTF` chỉ hỗ trợ payload tối đa 65.535 byte; nó **không phải** bộ mã hóa MUTF-8 tổng quát cho mọi `String` lớn.

**Tệp `EncodingProbe.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.StringJoiner;

public class EncodingProbe {
    private static final HexFormat HEX =
            HexFormat.ofDelimiter(" ").withUpperCase();

    public static void main(String[] args) throws Exception {
        String sample = "A" + '\0' + "\u00E9"
                + new String(Character.toChars(0x1F600));

        StringJoiner units = new StringJoiner(" ");
        for (int i = 0; i < sample.length(); i++) {
            units.add("%04X".formatted((int) sample.charAt(i)));
        }

        byte[] utf8 = sample.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeUTF(sample);
        }

        byte[] wire = buffer.toByteArray();
        byte[] modifiedUtf8 = Arrays.copyOfRange(wire, 2, wire.length);

        boolean restored;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            restored = sample.equals(in.readUTF());
        }

        System.out.println("UTF-16 units: " + units);
        System.out.println("Length/code points: " + sample.length()
                + "/" + sample.codePointCount(0, sample.length()));
        System.out.println("Standard UTF-8: " + HEX.formatHex(utf8));
        System.out.println("Modified UTF-8: " + HEX.formatHex(modifiedUtf8));
        System.out.println("writeUTF prefix: " + HEX.formatHex(wire, 0, 2));
        System.out.println("readUTF round-trip: " + restored);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 EncodingProbe.java
java EncodingProbe
```

**stdout (Java 17+):**

```text
UTF-16 units: 0041 0000 00E9 D83D DE00
Length/code points: 5/4
Standard UTF-8: 41 00 C3 A9 F0 9F 98 80
Modified UTF-8: 41 C0 80 C3 A9 ED A0 BD ED B8 80
writeUTF prefix: 00 0B
readUTF round-trip: true
```

Byte prefix `00 0B` là số nguyên 16-bit big-endian có giá trị **11**, biểu thị **11 byte payload MUTF-8**, không phải số UTF-16 code unit. `DataInputStream.readUTF` cần framing prefix như trên; `NewStringUTF` lại cần **MUTF-8 payload kèm byte NUL ở cuối**. Nếu truyền nguyên `wire` (bắt đầu `00 0B`) vào `NewStringUTF`, byte `00` đầu tiên bị coi là kết thúc C string: đây là hai giao thức khác nhau.

## 5. Các JNI API chuỗi và đơn vị đo

| JNI API (C) | Dạng dữ liệu | Độ dài/kết quả | Quy tắc sử dụng |
|---|---|---|---|
| `GetStringLength(env, s)` | UTF-16 | `jsize` = **số code unit** | Tương ứng `String.length()` |
| `GetStringChars(env, s, &isCopy)` | `const jchar *`; UTF-16 units | Dùng `GetStringLength`, **không giả định NUL terminator** | Gọi `ReleaseStringChars` sau khi dùng; có thể là copy |
| `GetStringRegion(env, s, start, len, buf)` | Copy vùng `jchar` | `start`, `len` đo UTF-16 code unit | Caller tự cấp phát đủ `len * sizeof(jchar)` và kiểm tra bounds |
| `NewString(env, chars, len)` | Input `jchar *` UTF-16 | `len` = số code unit; không cần kết thúc NUL | Dùng khi có UTF-16 code units, kể cả U+0000 |
| `GetStringUTFLength(env, s)` | MUTF-8 | `jsize` = **số byte MUTF-8** | Có từ JDK cũ; **deprecated từ JDK 24** vì giá trị có thể vượt `jsize` |
| `GetStringUTFLengthAsLong(env, s)` | MUTF-8 | `jlong` = **số byte MUTF-8** | Có từ **JDK 24**; phù hợp kiểm tra kích thước lớn |
| `GetStringUTFChars(env, s, &isCopy)` | `const char *` MUTF-8 | Dùng độ dài MUTF-8 tường minh | Gọi `ReleaseStringUTFChars`; không tự giả định UTF-8 chuẩn |
| `GetStringUTFRegion(env, s, start, len, buf)` | Copy MUTF-8 vào buffer | `start`/`len` đo **UTF-16 code unit**, kết quả có số **byte khác** | Đảm bảo buffer đủ; không trông chờ NUL terminator |
| `NewStringUTF(env, bytes)` | Input **MUTF-8 C string** | Đọc đến byte `00` cuối | Chỉ đưa MUTF-8 hợp lệ, không truyền UTF-8 chuẩn tùy ý |
| `GetStringCritical / ReleaseStringCritical` | Có thể pin/copy UTF-16 | Dùng theo UTF-16 units | Trong critical region không thực hiện JNI calls tùy ý hay thao tác gây block |

### Về giải phóng bộ nhớ

`GetStringChars` và `GetStringUTFChars` có thể trả pointer tới bản copy hoặc vùng native do JVM quản lý. Pointer chỉ hợp lệ đến khi gọi đúng `Release...` tương ứng. **Không** gọi `free()` trên pointer JNI trả về. Boolean `isCopy` là thông tin chẩn đoán, **không** thay đổi trách nhiệm release. Nếu JNI bị lỗi cấp phát và trả `NULL`, xử lý pending exception/điều kiện lỗi, không dereference.

`GetStringRegion` và `GetStringUTFRegion` viết vào buffer **do caller cung cấp**, nên không cần cặp `Release` tương ứng; ngược lại caller phải tự bảo đảm dung lượng, vòng đời và cách đo độ dài.

### Về kích thước lớn

Một `String` có thể có `GetStringLength` (UTF-16 units) nằm trong giới hạn `jsize` nhưng MUTF-8 dài **nhiều byte hơn**, nên `GetStringUTFLength` 32-bit không luôn biểu diễn được kích thước cần thiết. Kể từ JDK 24, `GetStringUTFLengthAsLong` cho phép đo bằng `jlong`; trước khi tạo `jbyteArray` hay cấp phát buffer C, vẫn phải kiểm tra giới hạn array/`size_t`/tràn số và dùng chiến lược chia khối nếu cần. Mọi đoạn demo ở đây chỉ dùng chuỗi rất ngắn nên API cũ đủ để minh họa Java 17+.

## 6. Thực hành JNI hoàn chỉnh: lấy UTF-16, MUTF-8 và tạo String từ MUTF-8

Ví dụ này xây một thư viện native nhỏ, cho Java nhìn thấy **chính các byte MUTF-8 mà JNI sinh ra**, và kiểm tra `NewStringUTF` tạo lại chuỗi Java có chứa NUL và emoji.

Môi trường để build: **JDK 17+, Linux, GCC và `JAVA_HOME` trỏ tới JDK**. Trên các hệ điều hành khác cần thay trình biên dịch/đuôi thư viện/đường dẫn JNI headers tương ứng.

### 6.1. Tệp `UtfBridgeDemo.java`

```java
import java.util.HexFormat;
import java.util.StringJoiner;

public class UtfBridgeDemo {
    static {
        System.loadLibrary("utfbridge");
    }

    private static native char[] utf16Units(String value);
    private static native byte[] modifiedUtf8Bytes(String value);
    private static native String createFromModifiedUtf8();

    public static void main(String[] args) {
        String input = "A" + '\0' + "\u00E9"
                + new String(Character.toChars(0x1F600));

        char[] units = utf16Units(input);
        StringJoiner unitsHex = new StringJoiner(" ");
        for (char unit : units) {
            unitsHex.add("%04X".formatted((int) unit));
        }

        byte[] modified = modifiedUtf8Bytes(input);

        System.out.println("JNI UTF-16: " + unitsHex);
        System.out.println("JNI MUTF-8: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(modified));
        System.out.println("NewStringUTF round-trip: "
                + input.equals(createFromModifiedUtf8()));
    }
}
```

Hai phương thức đầu nhận `String` và trả dữ liệu dạng `char[]`/`byte[]` chỉ để quan sát encoding. Phương thức cuối tạo `String` mới từ một dãy byte MUTF-8 hợp lệ có NUL terminator.

### 6.2. Sinh JNI header

```bash
javac -encoding UTF-8 -h . UtfBridgeDemo.java
```

Lệnh sinh `UtfBridgeDemo.class` và `UtfBridgeDemo.h`. Không tự đoán JNI symbol khi thay package, overload hoặc kiểu trả về; lấy prototypes từ header do `javac -h` tạo.

### 6.3. Tệp `UtfBridgeDemo.c`

```c
#include <jni.h>
#include "UtfBridgeDemo.h"

JNIEXPORT jcharArray JNICALL Java_UtfBridgeDemo_utf16Units(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;
    // Ví dụ yêu cầu value != NULL.
    jsize count = (*env)->GetStringLength(env, value);
    const jchar *units = (*env)->GetStringChars(env, value, NULL);
    if (units == NULL) return NULL;

    jcharArray result = (*env)->NewCharArray(env, count);
    if (result != NULL && count > 0) {
        (*env)->SetCharArrayRegion(env, result, 0, count, units);
    }

    // Luôn release, kể cả khi NewCharArray/SetCharArrayRegion lỗi.
    (*env)->ReleaseStringChars(env, value, units);
    if ((*env)->ExceptionCheck(env)) return NULL;
    return result;
}

JNIEXPORT jbyteArray JNICALL Java_UtfBridgeDemo_modifiedUtf8Bytes(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;
    // Chỉ dùng GetStringUTFLength với chuỗi ngắn trong demo.
    jsize count = (*env)->GetStringUTFLength(env, value);
    const char *bytes = (*env)->GetStringUTFChars(env, value, NULL);
    if (bytes == NULL) return NULL;

    jbyteArray result = (*env)->NewByteArray(env, count);
    if (result != NULL && count > 0) {
        (*env)->SetByteArrayRegion(
                env, result, 0, count, (const jbyte *) bytes);
    }

    (*env)->ReleaseStringUTFChars(env, value, bytes);
    if ((*env)->ExceptionCheck(env)) return NULL;
    return result;
}

JNIEXPORT jstring JNICALL Java_UtfBridgeDemo_createFromModifiedUtf8(
        JNIEnv *env, jclass owner) {
    (void) owner;

    // Payload: A + U+0000 + U+00E9 + U+1F600.
    // MUTF-8 có 11 byte dữ liệu và một byte 00 kết thúc C string.
    const char encoded[] = {
        0x41,
        (char) 0xC0, (char) 0x80,
        (char) 0xC3, (char) 0xA9,
        (char) 0xED, (char) 0xA0, (char) 0xBD,
        (char) 0xED, (char) 0xB8, (char) 0x80,
        '\0'
    };

    return (*env)->NewStringUTF(env, encoded);
}
```

Phần native **không** dùng `strlen` để đo MUTF-8 lấy từ JNI; nó copy đúng `count` byte bằng `SetByteArrayRegion`. Khi tạo `String` bằng `NewStringUTF`, đoạn C bảo đảm có byte `00` **ngoài payload** (chính là `'\0'` cuối mảng). Java trả về `String` với U+0000 **bên trong** và surrogate pair emoji nguyên vẹn.

Ví dụ ràng buộc `value != NULL`; ở hệ thống thật phải kiểm tra đầu vào Java và trạng thái exception. `NewCharArray`/`NewByteArray` có thể lỗi cấp phát; sau khi release, hàm trả reference `NULL` nếu có exception đang chờ.

### 6.4. Build thư viện và chạy

Trên Linux:

```bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libutfbridge.so UtfBridgeDemo.c

java -Djava.library.path=. UtfBridgeDemo
```

Trên **JDK 24+**, nếu JVM yêu cầu/cảnh báo quyền JNI native access, dùng:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. UtfBridgeDemo
```

**stdout mong đợi:**

```text
JNI UTF-16: 0041 0000 00E9 D83D DE00
JNI MUTF-8: 41 C0 80 C3 A9 ED A0 BD ED B8 80
NewStringUTF round-trip: true
```

Lưu ý: `System.loadLibrary("utfbridge")` dùng tên logic `utfbridge`; trên Linux file mặc định là `libutfbridge.so`. Với macOS có thể cần `libutfbridge.dylib` cùng JNI header `include/darwin`, với Windows cần `utfbridge.dll` và header `include/win32`. Không dùng nguyên lệnh GCC/Linux cho Windows khi không có toolchain tương đương.

## 7. Đường chuyển đổi ĐÚNG khi phía native cần UTF-8 chuẩn

Nhiều API native sử dụng **UTF-8 chuẩn**, chẳng hạn thư viện JSON, network protocol, filesystem API hoặc một C/C++ function nhận `(const uint8_t *data, size_t length)`. Không truyền con trỏ từ `GetStringUTFChars` vào những API này như thể nó là UTF-8 chuẩn.

### 7.1. Java → native API cần standard UTF-8

Ở Java, mã hóa **rõ charset** trước khi qua JNI:

```java
import java.nio.charset.StandardCharsets;

String text = "A" + '\0' + new String(Character.toChars(0x1F600));
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

// nativeSendUtf8(utf8, utf8.length); // native method tự khai báo.
```

Đây là **trích đoạn minh họa**, không phải chương trình độc lập. Trên phía C, nhận một `jbyteArray`, gọi `GetArrayLength` và `GetByteArrayRegion` (hoặc `GetByteArrayElements` kèm `ReleaseByteArrayElements`), rồi truyền **đúng số byte** đến API đích. Nếu native API cần NUL-terminated C string thì vẫn phải hiểu rằng **UTF-8 chuẩn cho phép `00` bên trong văn bản**; riêng hợp đồng của API C đó có thể không biểu diễn được embedded NUL. Cần từ chối ký tự NUL, dùng API có độ dài riêng hoặc thay đổi protocol, không tự làm mất dữ liệu bằng `strlen`.

Các thư viện native mong `wchar_t *` cũng không đồng nghĩa với `jchar *`. Trên một số hệ điều hành `wchar_t` là 16-bit, nơi khác là 32-bit; phải chuyển đổi theo ABI/platform, không cast tùy tiện.

### 7.2. Native UTF-8 chuẩn → Java String

Nếu C có dữ liệu UTF-8 chuẩn, đặc biệt chứa 4-byte sequence của emoji, **không** truyền thẳng nó vào `NewStringUTF`. Một đường đơn giản là đưa các byte ấy về Java dưới dạng `byte[]`, rồi giải mã bằng:

```java
String decoded = new String(utf8Bytes, StandardCharsets.UTF_8);
```

Dòng trên là trích đoạn khi biến `utf8Bytes` là `byte[]` nhận từ native. Constructor này có chính sách thay thế một số chuỗi byte không hợp lệ. Nếu dữ liệu đầu vào cần **được kiểm tra nghiêm ngặt**, dùng decoder với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }
}
```

Đây là **lớp utility độc lập** (có thể biên dịch bằng `javac StrictUtf8.java`) nhưng không chứa `main`. Gọi `StrictUtf8.decode(bytes)` từ ứng dụng/test. Khi truyền payload MUTF-8 có `C0 80` hay các surrogate bytes vào strict decoder, nó báo dữ liệu **không hợp lệ theo UTF-8 chuẩn**, thay vì âm thầm thay ký tự. 

Đường C-native → Java khác là decode UTF-8 thành các UTF-16 `jchar` đúng chuẩn (qua thư viện chuyển mã), rồi gọi `NewString(env, units, codeUnitCount)`. `NewString` nhận UTF-16 code units và **độ dài tường minh**, không cần NUL kết thúc.

## 8. Những bẫy đặc biệt ở NUL, surrogate và độ dài buffer

### Bẫy A: U+0000 không giống kết thúc String của Java

Trong Java, `"A" + '\0' + "B"` có độ dài **3 UTF-16 code units** và giữ nguyên U+0000 ở giữa. Khi mã hóa UTF-8 chuẩn, bytes là `41 00 42`. Truyền vào API C chỉ dùng `strlen` cho kết quả dài **1 byte**, vì nó dừng ở `00`. JNI MUTF-8 dùng `41 C0 80 42` để không có `00` trong payload; muốn gửi UTF-8 chuẩn thì phải có độ dài tường minh hoặc một chính sách NUL được định nghĩa rõ.

### Bẫy B: emoji không dài một `char` và không dài ba byte

Một emoji ngoài BMP có `String.length() == 2` nhưng có thể chỉ có **1 code point**; trong UTF-8 chuẩn thường **4 byte**, còn trong MUTF-8 **6 byte**. Cấp phát `length * 3` có thể là cận trên cho MUTF-8 của chuỗi ngắn, nhưng không phải kích thước thực và vẫn cần xét overflow, NUL terminator hoặc prefix. Đo chính xác theo API encoding tương ứng.

### Bẫy C: chuỗi chứa surrogate đơn lẻ

`String`/`char` có thể giữ một **high hoặc low surrogate không ghép cặp**. MUTF-8 có thể mã hóa riêng code unit đó thành 3 byte; **strict UTF-8** không chấp nhận surrogate code point. Khi Java chuyển sang UTF-8 chuẩn qua `getBytes(UTF_8)`, unmappable/malformed UTF-16 input có thể bị thay thế theo chính sách của encoder mặc định; nếu cần chống mất dữ liệu, chọn `CharsetEncoder` có `onMalformedInput(CodingErrorAction.REPORT)`.

Do đó, nếu yêu cầu "bảo toàn tuyệt đối mọi code unit của String", hãy dùng UTF-16 `jchar[]` hoặc protocol có quy tắc rõ cho unmatched surrogate; đừng mặc nhiên cho rằng round-trip Unicode scalar value sẽ giữ được mã UTF-16 không hợp lệ.

### Bẫy D: buffer của `GetStringUTFRegion`

`len` là **số UTF-16 code unit cần chuyển đổi**, không phải số byte ghi ra. Một đoạn có các ký tự nhiều byte có thể ghi **nhiều hơn `len` byte**. Kết quả cũng **không được bảo đảm NUL-terminated**. Vì vậy:

- Không cấp phát đúng `len` byte cho `GetStringUTFRegion`.
- Không truyền buffer vừa copy thẳng vào `strlen`/`printf("%s")` khi chưa biết kích thước và tự thêm terminator.
- Nếu dùng toàn bộ String nhỏ, có thể lấy byte count qua `GetStringUTFLength` trước; với đoạn con, cần tính/cấp phát đủ cho **đoạn đó** (và kiểm tra overflow), không lấy nhầm byte count toàn chuỗi làm số byte thực của region.
- Khi chỉ cần copy vài ký tự UTF-16, `GetStringRegion` đưa ra `jchar` có độ dài đơn vị rõ hơn.

### Bẫy E: giữ pointer JNI quá lâu

`GetStringChars` / `GetStringUTFChars` có thể cấp phát bản copy hoặc pin tài nguyên. Không giữ pointer sau `Release...`, không truyền pointer sang thread khác mà không thiết kế quản lý vòng đời, và không nhầm `isCopy == JNI_FALSE` với quyền sở hữu dữ liệu. `GetStringCritical` có các hạn chế nghiêm ngặt về JNI calls/blocking khi đang trong critical region; chỉ dùng khi thực sự cần và có đoạn code cực ngắn.

## 9. Chọn API theo mục đích

| Nhu cầu thực tế | Hướng xử lý |
|---|---|
| Đọc **UTF-16 code units** từ `jstring`, giữ U+0000 và surrogate | `GetStringLength` + `GetStringChars` + `ReleaseStringChars` hoặc `GetStringRegion` |
| Tạo `jstring` từ buffer UTF-16 16-bit | `NewString(env, chars, length)` |
| Giao tiếp với phần native được thiết kế cho **JNI MUTF-8** | `GetStringUTFChars` + `ReleaseStringUTFChars`; tạo từ MUTF-8 hợp lệ dùng `NewStringUTF` |
| Đo số **byte MUTF-8** | `GetStringUTFLength` ở JDK cũ, `GetStringUTFLengthAsLong` từ JDK 24 |
| Ghi file JSON, gửi HTTP/gRPC hoặc gọi API đòi **UTF-8 chuẩn** | `String.getBytes(StandardCharsets.UTF_8)` → `jbyteArray` + length; hoặc decoder/encoder chuẩn trên native |
| Nhận byte UTF-8 chuẩn từ native | `jbyteArray` → `new String(bytes, UTF_8)` hoặc strict decoder; có thể chuyển mã sang UTF-16 rồi `NewString` |
| Cần C API nhận string NUL-terminated nhưng văn bản có U+0000 | Điều chỉnh hợp đồng API hoặc từ chối NUL; **không** lén dùng MUTF-8 nếu C API yêu cầu standard UTF-8 |
| Muốn cache/cấp phát buffer lớn | Kiểm tra byte count, giới hạn kiểu `jsize`/`size_t`, tràn phép cộng và vòng đời; cân nhắc streaming/chunking |

Hãy xác định **encoding của API đích**, **đơn vị của length** và **ai chịu trách nhiệm free/release** trước khi chọn JNI function. JNI không thể tự đoán một thư viện C ngoài đang mong UTF-8 chuẩn, UTF-16, UTF-32 hay locale-dependent encoding.

## 10. Các lỗi phổ biến khi debug

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Chuỗi bị cắt ở U+0000 | Đưa UTF-8 chuẩn có `00` vào API C dùng `strlen` | In hex, kiểm tra length-based API |
| Emoji biến thành dấu hỏi/ký tự thay thế | Đọc MUTF-8 bằng UTF-8 decoder hoặc mã hóa surrogate lỗi | So hex 4-byte UTF-8 với 6-byte MUTF-8 |
| `NewStringUTF` crash hoặc tạo ký tự sai | Truyền UTF-8 chuẩn có 4-byte sequence, MUTF-8 sai hoặc thiếu terminator | Chỉ truyền MUTF-8 hợp lệ; thử `-Xcheck:jni` |
| Giá trị length lớn hơn dự kiến | Đếm byte thay vì code unit, hoặc ngược lại | Phân biệt `GetStringLength` / `GetStringUTFLength` |
| Native buffer bị ghi quá giới hạn | Dùng số UTF-16 units làm byte capacity cho `GetStringUTFRegion` | Cấp phát đủ byte output, kiểm tra overflow |
| Memory tăng qua nhiều lời gọi | Quên `ReleaseStringChars` / `ReleaseStringUTFChars` | Ghép acquire/release theo mọi nhánh lỗi |
| `readUTF` không hiểu bytes từ mạng | `readUTF` cần 2-byte prefix và MUTF-8, network dùng UTF-8 chuẩn không có prefix đó | Dùng charset decoder và framing protocol thực |
| Nội dung lỗi nhưng chỉ ở một vài ký tự | BMP ASCII/Latin có encoding trùng, NUL và non-BMP mới lộ khác biệt | Test A, U+0000, é, 😀, unmatched surrogate |

Khi debug JNI, ngoài log thông thường có thể bật `java -Xcheck:jni ...` để phát hiện một số lỗi sử dụng JNI; nó **không** thay thế kiểm tra byte protocol hay cơ chế memory safety. Không nên log trực tiếp binary buffer bằng `%s` khi chưa biết nó có NUL terminator; dùng hex dump giới hạn độ dài.

## 11. Bài tập có đáp án

**Bài 1.** `String s = "A" + '\0' + "B";` có `s.length()` bằng bao nhiêu? UTF-8 chuẩn và MUTF-8 bao nhiêu byte?

**Đáp án:** 3 UTF-16 units. UTF-8 chuẩn: `41 00 42` (3 byte). MUTF-8: `41 C0 80 42` (4 byte). Nếu mã hóa bằng `DataOutputStream.writeUTF`, trên wire còn thêm 2 byte prefix `00 04`.

**Bài 2.** Cho `String s = new String(Character.toChars(0x1F600));`. Dự đoán `s.length()`, số code point, số byte UTF-8 chuẩn và số byte JNI MUTF-8.

**Đáp án:** `length()=2`, `codePointCount(...)=1`, UTF-8 chuẩn 4 byte `F0 9F 98 80`, MUTF-8 6 byte `ED A0 BD ED B8 80`.

**Bài 3.** Một C API nhận JSON dạng UTF-8 chuẩn có độ dài tường minh. Nên truyền `GetStringUTFChars(env, text, ...)` hay `jbyteArray` được mã hóa bằng `StandardCharsets.UTF_8`?

**Đáp án:** Chọn `jbyteArray` chuẩn + độ dài. `GetStringUTFChars` trả MUTF-8 và có thể sai chuẩn với NUL/supplementary characters.

**Bài 4.** Tại sao `GetStringUTFRegion(env, s, 0, s.length(), buf)` vào buffer dài đúng `s.length()` có thể hỏng memory?

**Đáp án:** `s.length()` là số UTF-16 code units, nhưng MUTF-8 output thường có nhiều byte cho một unit. Phải biết/gán dung lượng theo **số byte encoded**, kiểm tra overflow và không giả định byte NUL kết thúc.

**Bài 5.** Có thể đưa trực tiếp byte array từ `DataOutputStream.writeUTF` vào `NewStringUTF` không?

**Đáp án:** Không. `writeUTF` thêm **2-byte length prefix**; `NewStringUTF` nhận **MUTF-8 C string** kết thúc NUL. Phải tách framing và chuẩn bị terminator hợp lệ. Với chuỗi lớn hơn 65.535 byte MUTF-8, `writeUTF` còn ném `UTFDataFormatException`.

## 12. Kết luận thực hành và tài liệu gốc

Quy tắc đủ để tránh phần lớn lỗi encoding ở ranh giới Java–JNI là:

1. **Java `String` / `jchar`:** quan sát theo **UTF-16 code units**; `length()` không nhất thiết là số ký tự người đọc thấy.
2. **JNI `...UTF...`:** là **Modified UTF-8**, với U+0000 → `C0 80` và supplementary code point → **6 byte**, vì mã hóa từng surrogate.
3. **I/O, web, file, JSON dùng UTF-8 chuẩn:** mã hóa/giải mã bằng charset chuẩn hoặc converter tương đương; không đưa MUTF-8 trực tiếp sang giao thức UTF-8 chuẩn.
4. **Memory và length:** byte count khác unit count, buffer pointer phải được release đúng JNI contract, còn C string terminator và framing prefix là hai khái niệm khác nhau.

Tài liệu chuẩn để đối chiếu API và hành vi:

- [Oracle JNI Specification — Types and Data Structures / Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html#modified-utf-8-strings)
- [Oracle JNI Specification — JNI Functions / String Operations](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations)
- [Java 17 — `DataOutputStream.writeUTF`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html#writeUTF(java.lang.String))
- [Java 17 — `String`, `length`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java 17 — `StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java 17 — `CharsetDecoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
