# Con trỏ, vùng nhớ kích thước không xác định và trách nhiệm khi dùng reinterpret

## 1. Vì sao một con trỏ được biểu diễn bằng segment có kích thước 0?

Foreign Function and Memory API (FFM API) biểu diễn địa chỉ native bằng `MemorySegment`. Một segment thông thường chứa cả địa chỉ, kích thước vùng nhớ và scope xác định thời gian được phép truy cập. Tuy nhiên, khi một hàm native trả về con trỏ, Java thường chỉ nhận được địa chỉ bắt đầu; kích thước vùng nhớ và thời gian vùng nhớ còn hợp lệ phụ thuộc vào hợp đồng của thư viện native.

Ví dụ, một hàm C có kiểu trả về `char*` có thể trả về:

- Con trỏ đến một ký tự đơn.
- Con trỏ đến mảng ký tự có độ dài được trả về qua tham số khác.
- Con trỏ đến chuỗi kết thúc bằng ký tự `\0`.
- Con trỏ đến vùng nhớ do thư viện quản lý và chỉ hợp lệ cho đến lần gọi tiếp theo.

Chỉ nhìn vào địa chỉ không thể biết trường hợp nào đang xảy ra. Vì vậy, FFM API dùng **zero-length memory segment** (segment có kích thước 0) để đại diện cho con trỏ mà kích thước vùng nhớ chưa được xác định. Segment này giữ địa chỉ nhưng không cho phép đọc hoặc ghi trực tiếp.

Đây là một giới hạn an toàn có chủ ý: khi chưa biết kích thước vùng nhớ, JVM không thể kiểm tra một thao tác truy cập có nằm trong giới hạn hợp lệ hay không. Lập trình viên phải chủ động cung cấp thông tin kích thước và vòng đời trước khi dereference con trỏ.

## 2. Khi nào FFM API tạo zero-length segment?

Zero-length segment được dùng trong các trường hợp phổ biến sau:

1. Một foreign function trả về con trỏ.
2. Một con trỏ được truyền từ native code vào Java qua upcall stub.
3. Java đọc một địa chỉ từ segment khác bằng `get(ValueLayout.ADDRESS, offset)`.

Ví dụ, đọc một trường con trỏ trong cấu trúc native:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

static MemorySegment readPointer(MemorySegment nativeStruct, long pointerOffset) {
    return nativeStruct.get(ValueLayout.ADDRESS, pointerOffset);
}
```

`get(ValueLayout.ADDRESS, pointerOffset)` trả về một native segment biểu diễn địa chỉ được lưu tại offset đó. Trong trường hợp không gắn target layout, segment trả về có `byteSize() == 0` và thuộc global scope. Có thể truyền segment này như một con trỏ cho foreign function khác, nhưng không thể đọc dữ liệu qua nó.

```java
MemorySegment pointer = readPointer(nativeStruct, pointerOffset);

System.out.println(pointer.byteSize()); // 0

if (pointer.address() == 0L) {
    // Đây là con trỏ NULL; xử lý theo hợp đồng của API native.
    return;
}

// Không đọc trực tiếp từ pointer ở đây: segment có kích thước 0.
```

`MemorySegment.NULL` là segment kích thước 0 đại diện cho địa chỉ null. Có thể kiểm tra địa chỉ bằng `pointer.address() == 0L`; tránh so sánh danh tính đối tượng bằng `==` với `MemorySegment.NULL`.

## 3. Kích thước và vòng đời là hai thông tin độc lập

Một segment có hai giới hạn quan trọng:

- **Spatial bounds (giới hạn không gian):** địa chỉ bắt đầu và số byte có thể truy cập.
- **Temporal bounds (giới hạn thời gian):** scope quyết định segment còn hợp lệ hay đã hết vòng đời.

Zero-length segment không có giới hạn không gian hữu ích để dereference. Đồng thời, con trỏ từ native function hoặc đọc từ một segment thường gắn với global scope. Global scope khiến bản thân wrapper không hết hiệu lực theo thời gian, nhưng **không bảo đảm vùng nhớ native phía sau vẫn còn được cấp phát**.

Ví dụ: thư viện native trả về con trỏ đến buffer nội bộ và cam kết buffer chỉ hợp lệ đến lần gọi API tiếp theo. Java có thể giữ zero-length segment lâu hơn thời hạn đó, nhưng địa chỉ đã trở thành con trỏ treo (*dangling pointer*). Scope của segment không thể tự phát hiện thư viện đã thu hồi hoặc tái sử dụng vùng nhớ.

Trước khi sử dụng con trỏ, phải xác định từ hợp đồng native:

- Kích thước vùng nhớ tính bằng byte hoặc số phần tử.
- Cách xác định kích thước: tham số riêng, trường độ dài, layout cố định, sentinel có giới hạn, hay quy tắc khác.
- Ai sở hữu vùng nhớ và ai có trách nhiệm giải phóng.
- Vùng nhớ còn hợp lệ đến thời điểm nào, có bị thư viện ghi đè hoặc thu hồi khi gọi hàm khác không.
- Quy tắc đồng bộ nếu nhiều thread cùng truy cập.

Nếu API native không cung cấp đủ thông tin để xác định kích thước và thời gian hợp lệ, hãy giữ con trỏ ở dạng opaque và chỉ chuyển nó đến hàm native có hợp đồng phù hợp. Không tự đoán kích thước từ địa chỉ.

## 4. `reinterpret(long)`: gán lại giới hạn kích thước

`MemorySegment.reinterpret(long newSize)` tạo một segment mới có cùng địa chỉ và scope với segment ban đầu, nhưng có kích thước `newSize`:

```java
MemorySegment zeroLength = nativeStruct.get(ValueLayout.ADDRESS, pointerOffset);

// Chỉ hợp lệ nếu hợp đồng native xác nhận vùng nhớ tại địa chỉ này
// có ít nhất 16 byte và còn sống trong suốt thời gian sử dụng.
MemorySegment bytes = zeroLength.reinterpret(16);

int firstValue = bytes.get(ValueLayout.JAVA_INT, 0);
```

`reinterpret` không cấp phát vùng nhớ mới, không sao chép dữ liệu, không thay đổi địa chỉ và cũng không giải phóng vùng nhớ. Nó chỉ tạo một cách nhìn (*view*) mới trên cùng vùng nhớ với giới hạn kích thước do lập trình viên cung cấp.

Vì zero-length segment thường có global scope, `reinterpret(16)` cũng giữ global scope. Segment mới có thể truy cập từ nhiều thread và không tự hết hiệu lực khi thư viện native giải phóng buffer. Do đó, `reinterpret(long)` chỉ thay đổi giới hạn không gian; nó không giải quyết quyền sở hữu hoặc vòng đời của tài nguyên native.

Nếu `newSize` âm, phương thức ném `IllegalArgumentException`. Nếu segment không phải native segment, phương thức ném `UnsupportedOperationException`. Dù `newSize` không âm và lời gọi thành công, Java vẫn không xác minh vùng nhớ thực tế có đủ byte như vậy hay không.

## 5. Xác định kích thước trước khi reinterpret

Thông tin kích thước thường đến từ một tham số hoặc trường dữ liệu khác do native API cung cấp. Ví dụ, một hàm trả về con trỏ mảng số nguyên cùng với số phần tử:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

static void readNativeIntArray(
        MemorySegment pointer,
        long elementCount) {

    if (pointer.address() == 0L) {
        if (elementCount == 0) {
            return; // Quy tắc này phải phù hợp với hợp đồng native.
        }
        throw new IllegalStateException("Native API trả về NULL");
    }

    if (elementCount < 0) {
        throw new IllegalArgumentException("Số phần tử âm");
    }

    long byteSize = Math.multiplyExact(
            elementCount,
            ValueLayout.JAVA_INT.byteSize());

    // Native owner phải bảo đảm buffer còn hợp lệ trong khối này.
    try (Arena accessArena = Arena.ofConfined()) {
        MemorySegment values = pointer.reinterpret(byteSize, accessArena, null);

        for (long i = 0; i < elementCount; i++) {
            int value = values.getAtIndex(ValueLayout.JAVA_INT, i);
            System.out.println(value);
        }
    }
}
```

`Math.multiplyExact` giúp phát hiện tràn số khi đổi số phần tử thành số byte. Việc kiểm tra `elementCount` không âm cũng ngăn dữ liệu độ dài sai đi vào phép tính. Những kiểm tra này chỉ bảo vệ phép tính phía Java; chúng vẫn không chứng minh con trỏ thật sự trỏ đến một vùng nhớ đủ lớn. Điều đó phải được bảo đảm bởi native API.

Trong ví dụ, `reinterpret(byteSize, accessArena, null)` gắn segment mới với scope của `accessArena`. Khi arena đóng, Java không cho phép truy cập segment mới nữa. `null` có nghĩa là không đăng ký cleanup action. Arena này chỉ giới hạn thời gian Java được phép truy cập; nó **không tự giải phóng** buffer do thư viện native sở hữu.

## 6. `reinterpret(long, Arena, Consumer)`: gắn kích thước, scope và cleanup

Khi Java nhận một vùng nhớ native do chính native allocator cấp phát và ứng dụng có trách nhiệm giải phóng, có thể gắn vòng đời vùng nhớ với một arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.util.function.Consumer;

static MemorySegment manageNativeAllocation(
        MemorySegment rawPointer,
        long byteSize,
        Arena owner,
        Consumer<MemorySegment> nativeFree) {

    if (rawPointer.address() == 0L) {
        throw new OutOfMemoryError("Native allocator trả về NULL");
    }
    if (byteSize < 0) {
        throw new IllegalArgumentException("Kích thước không hợp lệ");
    }

    return rawPointer.reinterpret(byteSize, owner, nativeFree);
}
```

Ở đây `nativeFree` là cleanup action gọi đúng hàm giải phóng do thư viện cấp, chẳng hạn `free` tương ứng với `malloc`. Khi `owner.close()` được gọi, scope của segment bị vô hiệu hóa và cleanup action được thực thi để trả vùng nhớ cho native allocator.

Overload này thực hiện ba việc:

1. Giữ nguyên địa chỉ con trỏ.
2. Gán giới hạn kích thước `byteSize` do chương trình cung cấp.
3. Gắn segment với scope của `owner` và đăng ký cleanup action chạy khi scope đó bị đóng.

Cleanup action nhận một `MemorySegment` mới đại diện cùng địa chỉ và kích thước, nhưng thuộc global scope và có thể truy cập từ bất kỳ thread nào. Vì vậy, cleanup có thể truyền segment đó cho foreign function `free`. Không để cleanup action rò rỉ segment này cho code khác, vì vùng nhớ có thể đã bị giải phóng ngay sau khi cleanup hoàn tất.

Hãy chỉ dùng cleanup để giải phóng tài nguyên mà Java thực sự sở hữu. Nếu thư viện native giữ quyền sở hữu và tự giải phóng buffer, không đăng ký thêm `free`; nếu không, có thể xảy ra lỗi giải phóng hai lần (*double free*). Nếu cleanup ném exception, thao tác đóng arena cũng có thể thất bại bằng runtime exception.

## 7. Overload đổi scope mà không truyền kích thước

FFM API còn có `reinterpret(Arena arena, Consumer<MemorySegment> cleanup)`. Overload này giữ địa chỉ, gắn segment với scope của arena được cung cấp và đăng ký cleanup action. Nó không nhận đối số `newSize`; với zero-length pointer, API trả về segment có kích thước không giới hạn.

Kích thước không giới hạn không có nghĩa Java đã phát hiện kích thước thật của allocation. Nó chỉ có nghĩa giới hạn không gian đã bị gỡ bỏ. Chỉ dùng dạng này nếu hợp đồng native bảo đảm cách truy cập không cần giới hạn kích thước hữu hạn và lập trình viên có thể chứng minh mọi phép truy cập đều hợp lệ. Với mảng hoặc cấu trúc có kích thước xác định, nên ưu tiên overload có `newSize` để giữ giới hạn không gian rõ ràng.

## 8. Khi kích thước đã biết tĩnh: `AddressLayout.withTargetLayout`

Nếu kích thước vùng nhớ đích được biết ngay khi định nghĩa layout, có thể gắn target layout vào `AddressLayout`. Khi đọc con trỏ, FFM API sẽ tạo segment có kích thước bằng `targetLayout.byteSize()` thay vì zero-length segment:

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

AddressLayout fourIntsPointer = ValueLayout.ADDRESS.withTargetLayout(
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_INT));

MemorySegment fourInts = nativeStruct.get(fourIntsPointer, pointerOffset);
int last = fourInts.getAtIndex(ValueLayout.JAVA_INT, 3);
```

Đoạn này mô tả con trỏ đến đúng bốn phần tử `int`. Đây là cách phù hợp khi layout đích cố định và đáng tin cậy. `AddressLayout.withTargetLayout` cũng là restricted method, vì vậy vẫn cần native access được bật. Nếu kích thước chỉ biết lúc chạy, hãy lấy kích thước từ hợp đồng native rồi dùng `reinterpret(newSize)` hoặc overload có arena phù hợp.

## 9. Vì sao `reinterpret` là restricted method?

Các thao tác truy cập `MemorySegment` bình thường được JVM kiểm tra dựa trên địa chỉ, kích thước và scope. `reinterpret` cho phép lập trình viên thay đổi các giới hạn này mà JVM không thể xác minh vùng nhớ vật lý thực sự có hợp lệ hay không.

Nếu gán kích thước lớn hơn vùng allocation, thao tác đọc hoặc ghi có thể truy cập sang vùng nhớ khác, làm hỏng dữ liệu native, gây crash JVM hoặc tạo lỗi bảo mật. Nếu gán scope dài hơn vòng đời allocation, chương trình có thể truy cập vùng nhớ đã bị giải phóng (*use-after-free*). Vì vậy, `reinterpret` được đánh dấu là restricted method và chỉ dùng được khi module gọi đã bật native access.

Với ứng dụng chạy trên classpath (unnamed module), có thể bật native access bằng:

```bash
java --enable-native-access=ALL-UNNAMED -cp out com.example.Main
```

Với ứng dụng dùng named module, chỉ định tên module:

```bash
java --enable-native-access=com.example.app -m com.example.app/com.example.Main
```

Nếu module gọi restricted method chưa được cấp native access, Java ném `IllegalCallerException`. Đây không phải cờ preview; nó là quyền cho phép module sử dụng các API native/restricted.

## 10. Checklist trước khi dereference một con trỏ

Trước khi gọi `reinterpret` hoặc đọc/ghi qua segment đại diện con trỏ, hãy xác nhận:

1. **Con trỏ không null:** kiểm tra `pointer.address() != 0L` theo quy tắc của API native.
2. **Kích thước có nguồn đáng tin cậy:** lấy từ tài liệu thư viện, tham số độ dài, trường cấu trúc hoặc layout cố định. Không suy đoán từ địa chỉ.
3. **Tính toán kích thước không tràn:** kiểm tra số phần tử và dùng `Math.multiplyExact` khi nhân với kích thước phần tử.
4. **Alignment phù hợp:** địa chỉ phải đáp ứng yêu cầu căn chỉnh của layout được dùng khi truy cập.
5. **Quyền sở hữu rõ ràng:** biết ai cấp phát và ai phải giải phóng. Chỉ gọi đúng allocator/deallocator theo cặp.
6. **Thời gian sống đủ dài:** vùng nhớ phải còn hợp lệ trong toàn bộ thời gian Java hoặc native code sử dụng nó.
7. **Scope phù hợp:** dùng arena để giới hạn thời gian Java truy cập; hiểu rằng scope không tự giữ cho allocation do bên ngoài quản lý còn sống.
8. **Cleanup an toàn:** nếu đăng ký cleanup, không giải phóng hai lần và không làm rò rỉ segment được truyền cho cleanup.
9. **Native access được bật:** module gọi `reinterpret` hoặc `withTargetLayout` phải được cấp quyền tương ứng.

Nếu không chứng minh được kích thước và thời gian sống của vùng nhớ, đừng dereference con trỏ. Hãy yêu cầu native API cung cấp độ dài hoặc một hàm truy cập có kiểm tra thay vì mở rộng giới hạn segment theo phỏng đoán.

## 11. Phạm vi API và tài liệu tham khảo

Foreign Function and Memory API trở thành API chính thức trong Java 22 thông qua JEP 454. `MemorySegment.reinterpret` và `AddressLayout.withTargetLayout` vẫn xuất hiện trong tài liệu Java SE hiện hành, nhưng được đánh dấu restricted vì có thể phá vỡ bảo đảm an toàn bộ nhớ nếu dùng sai. Bài này chỉ dùng các chữ ký API đã được chuẩn hóa, không sử dụng các tên API preview cũ như `MemoryAddress` hoặc `ResourceScope`.

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — trạng thái và thiết kế API chính thức từ Java 22.
- [Java SE 22 API: MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html) — zero-length segment, `get(AddressLayout, long)` và các overload `reinterpret`.
- [Java SE 26 API: MemorySegment](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/MemorySegment.html) — hợp đồng hiện hành, cảnh báo restricted methods và trách nhiệm cleanup.
- [Java SE 26 API: Linker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Linker.html) — ví dụ quản lý con trỏ trả về từ foreign function và giải phóng native allocation bằng cleanup action.
- [Oracle Java SE 26 Core Libraries Guide: Foreign Functions That Return Pointers](https://docs.oracle.com/en/java/javase/26/core/java-core-libraries-developer-guide.pdf) — hướng dẫn về con trỏ, kích thước vùng nhớ và vòng đời tài nguyên native.
