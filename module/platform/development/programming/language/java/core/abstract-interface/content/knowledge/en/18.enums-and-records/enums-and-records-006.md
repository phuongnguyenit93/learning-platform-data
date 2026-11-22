# Limitations When Using `record` or `enum` in a `sealed` Hierarchy

## Objective

Since Java 17, `sealed class` and `sealed interface` allow explicitly declaring which types are permitted to extend or implement them directly. `record` and `enum` have their own inheritance rules, so they are suitable as leaf branches of a sealed hierarchy in certain ways, but they cannot arbitrarily replace a base class.

Key takeaway: **records and enums can implement a sealed interface; they cannot extend a user-defined sealed class.**

## 1. Rules of a Sealed Hierarchy

A class or interface declared `sealed` must specify the permitted direct subtypes with a `permits` clause, or let the compiler infer that list when matching direct subtypes are declared in the same compilation unit.

Example:

```java
sealed interface KetQua permits ThanhCong, ThatBai, TrangThai {
}
```

The listed types must be direct subtypes of `KetQua`: a class must `implements KetQua`, or another interface must `extends KetQua`. Do not list grandchild types that only inherit through an intermediate type.

Each direct subclass of a sealed class must be `final`, `sealed`, or `non-sealed`. For a sealed interface, the same rule applies to directly implementing classes and directly extending interfaces. The purpose is for each branch to either remain closed or explicitly open the hierarchy.

Permitted extending or implementing types must be in the same module as the sealed type when using a named module; if the application is in an unnamed module, they must be in the same package. Violating this condition will cause the program not to compile.

## 2. Why Can't a Record Be a Subclass of a Sealed Class?

A record always extends `java.lang.Record` directly. The record declaration syntax does not allow choosing another superclass. A record is also **implicitly `final`**, so it cannot be declared `sealed` or `non-sealed`, nor can subclasses be created from a record.

Therefore, a record cannot directly extend a custom sealed class. Even if the sealed class lists the record name in `permits`, that does not change the fixed superclass rule of records.

A record can implement a regular interface or a sealed interface. This is the appropriate way to represent an immutable data branch in a closed type hierarchy.

```java
sealed interface ThongTin permits NguoiDung {
}

record NguoiDung(String ten, int tuoi) implements ThongTin {
}
```

In this example, `NguoiDung` is a valid direct subtype of `ThongTin`. The record does not need to be declared `final` because that property is already implicitly applied by the language.

If you need to share state or behavior from a base class, use a regular class as a child branch of the sealed class. If the model mainly consists of data variants, a sealed interface combined with records is usually simpler.

## 3. Why Can't an Enum Be a Subclass of a Sealed Class?

Every enum inherits from `java.lang.Enum`, and Java does not allow an enum to extend another class. Therefore, an enum cannot directly extend an application-defined sealed class.

An enum can implement multiple interfaces, including sealed interfaces. This is useful when finite values such as statuses or event types need to participate in the same result model.

```java
sealed interface TrangThaiXuLy permits TrangThaiDonHang {
}

enum TrangThaiDonHang implements TrangThaiXuLy {
    MOI,
    DANG_XU_LY,
    HOAN_TAT
}
```

When no enum constant declares its own class body, the enum is implicitly `final`. If at least one enum constant has its own class body, the enum type is considered implicitly `sealed`; the anonymous classes associated with those constants are compiler-generated subclasses. This case does not turn the enum into a class that users can arbitrarily extend, and does not allow the enum to extend a custom sealed class.

## 4. Complete Example: Sealed Interface Combining Records and Enums

The example below runs standalone on Java 17 or later. Two records carry data for different results, while an enum represents a fixed state. All three implement the same sealed interface.

Save the contents to the file `SealedRecordEnumDemo.java`:

```java
import java.util.List;

public class SealedRecordEnumDemo {
    public static void main(String[] args) {
        List<KetQua> ketQua = List.of(
            new ThanhCong("OK", 200),
            new ThatBai("NOT_FOUND", 404),
            TrangThai.DANG_XU_LY
        );

        for (KetQua item : ketQua) {
            System.out.println(moTa(item));
        }
    }

    private static String moTa(KetQua item) {
        if (item instanceof ThanhCong t) {
            return "Thành công: " + t.ma() + " (" + t.httpCode() + ")";
        }
        if (item instanceof ThatBai f) {
            return "Thất bại: " + f.ma() + " (" + f.httpCode() + ")";
        }
        if (item instanceof TrangThai s) {
            return "Trạng thái: " + s.name();
        }

        throw new IllegalStateException(
            "Loại kết quả chưa được xử lý: " + item.getClass().getName()
        );
    }
}

sealed interface KetQua permits ThanhCong, ThatBai, TrangThai {
}

record ThanhCong(String ma, int httpCode) implements KetQua {
}

record ThatBai(String ma, int httpCode) implements KetQua {
}

enum TrangThai implements KetQua {
    DANG_XU_LY
}
```

Compile and run:

```text
javac -encoding UTF-8 SealedRecordEnumDemo.java
java SealedRecordEnumDemo
```

Expected standard output:

```text
Thành công: OK (200)
Thất bại: NOT_FOUND (404)
Trạng thái: DANG_XU_LY
```

The example shows that the sealed interface controls the set of directly implementing types, while records and enums retain their own rules. The `instanceof` statement uses pattern matching syntax that has been officially supported since Java 16, so the example does not require preview features.

## 5. Invalid Designs and How to Choose a Model

| Requirement | Appropriate Design | Limitation to Remember |
|---|---|---|
| A data variant consisting of fixed fields | A record implementing a sealed interface | A record cannot extend a custom base class |
| A finite set of states with fixed names | An enum implementing a sealed interface | An enum cannot extend a custom base class |
| Branches that need to inherit state or behavior from a superclass | Regular classes listed in `permits` | Each direct subclass must be `final`, `sealed`, or `non-sealed` |
| A branch that needs further extension while still controlling subtypes | An intermediate sealed class or sealed interface | The intermediate type must also declare its valid branches |
| Need to allow external subclasses to be added | A `non-sealed` branch or a non-sealed interface design | A `non-sealed` branch opens that part of the hierarchy beyond the closed list |

You cannot declare a record like `record ChiTiet(...) extends LopCoSo`: records do not have an `extends` clause for application classes. Similarly, declaring an enum to extend `LopCoSo` is invalid because enums already inherit from `java.lang.Enum`.

Another common mistake is putting a non-direct subtype into `permits`, or placing a permitted type in the wrong package/module. Check the actual inheritance relationship and declaration location of each type before investigating other errors.

## 6. How to Check When Compilation Reports Errors

1. Determine whether the parent type is a sealed class or a sealed interface.
2. For each entry in `permits`, check whether that type directly `extends` or `implements` the sealed type.
3. If the subtype is a record or enum, check whether it is trying to extend an application class. In that case, switch the model to a sealed interface or use a regular subclass.
4. For a regular direct subclass, check the `final`, `sealed`, or `non-sealed` modifier.
5. Check the same-module/same-package conditions and the type names in `permits`.
6. Recompile all related files together with the appropriate JDK version; do not draw conclusions from a single file if dependent types have not been compiled yet.

In Java 17, sealed classes/interfaces and records are already standard features. If you want to use `switch` with pattern matching over a sealed hierarchy, note that pattern matching for switch only became a standard feature in Java 21; in Java 17 it was still a preview feature. The examples in this article use `instanceof` so they can run without enabling preview.

## Key Takeaways

- **Record → sealed interface:** valid; a record is an implicitly `final` leaf branch.
- **Enum → sealed interface:** valid; an enum represents a finite set of constants and can be implicitly `final` or `sealed` depending on the class bodies of its constants.
- **Record → custom sealed class:** invalid because a record only extends `java.lang.Record`.
- **Enum → custom sealed class:** invalid because an enum only extends `java.lang.Enum`.
- **Sealed class → regular subclass:** valid if the subclass is permitted and complies with the modifier rules and module/package conditions.

Choose a sealed interface when you want to combine different leaf types such as records and enums; choose a sealed class when the branches need to share a specific superclass.
