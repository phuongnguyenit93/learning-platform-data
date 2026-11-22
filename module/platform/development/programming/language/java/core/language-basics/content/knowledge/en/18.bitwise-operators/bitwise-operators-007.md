# Bit Masks to Read, Set, Clear, and Toggle Flags — Java 17+

## 1. What Is a Bit Mask?

A **bit mask** is an integer whose 0/1 bits are used to select or manipulate specific bit positions in another integer. Each bit can represent an independent **flag**: an enabled feature, a state, or an attribute.

Example storing four flags in a single `int` variable:

| Flag | Bit index | Decimal value | 4-bit binary |
|---|---:|---:|---|
| `READ` | 0 | 1 | `0001` |
| `WRITE` | 1 | 2 | `0010` |
| `EXECUTE` | 2 | 4 | `0100` |
| `ADMIN` | 3 | 8 | `1000` |

~~~java
static final int READ    = 1 << 0;
static final int WRITE   = 1 << 1;
static final int EXECUTE = 1 << 2;
static final int ADMIN   = 1 << 3;

int flags = READ | WRITE; // 0001 | 0010 = 0011 (3)
~~~

Each flag has **its own dedicated `1` bit**, so they can be combined using `|` without losing information about the other flags. `flags` is now 3, meaning both READ and WRITE are set.

**Four core operations:**

- **Read/check:** `flags & mask`.
- **Set:** `flags | mask`.
- **Clear:** `flags & ~mask`.
- **Toggle:** `flags ^ mask`.

These operations apply to integral types `byte`, `short`, `char`, `int`, and `long` under Java's numeric promotion rules; the primary examples in this lesson use `int`.

## 2. From Bitwise Operations to Flag Operations

The four formulas follow directly from how each operator handles bits at the same position: AND (`&`) keeps 1 only when both bits are 1; OR (`|`) sets 1 if either bit is 1; XOR (`^`) flips the bit where the mask is 1; NOT (`~`) inverts every bit of the promoted operand.

~~~text
  flags      0101
  mask       0011
  &          0001   (filter common bits)
  |          0111   (set selected bits)
  ^          0110   (toggle selected bits)
~~~

The full truth tables belong to the lesson on AND/OR/XOR/NOT. What matters here is the **effect on flag state**: use `&` to check, `|` to set, `& ~mask` to clear, and `^` to toggle. On `int`, `~` inverts all 32 bits, so it is usually paired with `&` or a mask limiting the target bit region.

## 3. Reading a Single Flag: AND with a Mask

To check whether the READ flag is set:

~~~java
boolean canRead = (flags & READ) != 0;
~~~

If `flags = 0b0101` (READ and EXECUTE), we have:

~~~text
flags = 0101
READ  = 0001
&     = 0001  -> non-zero -> READ is set
~~~

For WRITE:

~~~text
flags = 0101
WRITE = 0010
&     = 0000  -> zero -> WRITE is cleared
~~~

**Parentheses are critical for clarity:** write `(flags & READ) != 0`, never the ambiguous `flags & READ != 0`. In Java, `!=` has higher precedence than `&`; without parentheses, the expression attempts a bitwise AND between an `int` and a `boolean` and fails to compile.

If the mask is a **single bit**, the following two checks are equivalent:

~~~java
(flags & READ) != 0
(flags & READ) == READ
~~~

With a **multi-bit mask**, however, the two expressions mean different things, as shown next.

## 4. Reading Multiple Flags: Distinguishing "Any" vs. "All"

Suppose:

~~~java
int flags = READ | WRITE;       // 0011
int required = READ | EXECUTE;  // 0101
~~~

**Has at least one flag in the mask:** (*any*):

~~~java
boolean any = (flags & required) != 0; // true: READ is set
~~~

**Has every flag in the mask:** (*all*):

~~~java
boolean all = (flags & required) == required; // false: EXECUTE is not set
~~~

| Check | Formula | When is it true? |
|---|---|---|
| **Single flag** | `(flags & FLAG) != 0` | The bit for FLAG is set |
| **Any flag** | `(flags & mask) != 0` | At least one bit in `mask` is set |
| **All flags** | `(flags & mask) == mask` | Every bit in `mask` is set |
| **No flags** | `(flags & mask) == 0` | No bit in `mask` is set |

**Zero-mask pitfall:** `(flags & 0) == 0` is **always true**, even when `flags == 0`. Thus `hasAll(flags, 0)` can return true vacuously (no required flags). If your business API does not permit an empty mask, **validate `mask != 0`**, and never treat a vacuous `true` as a valid permission state.

## 5. Setting Flags with OR

Turn on selected bits while leaving all other bits unchanged:

~~~java
flags = flags | READ;
flags |= READ; // Shorthand, same intent for a simple int variable
~~~

Example:

~~~text
flags  = 0100   (EXECUTE)
mask   = 0011   (READ | WRITE)
OR     = 0111   (all three set)
~~~

~~~java
int flags = EXECUTE;
flags |= READ | WRITE;
System.out.println(flags); // 7
~~~

**Idempotence:** setting a flag that is already set **does not change the value**:

~~~java
flags |= READ;
flags |= READ; // still keeps READ set, does not turn it off
~~~

If you want to **flip** the state on every call, use XOR `^`, not OR.

## 6. Clearing Flags with AND NOT

To clear the bits in `mask` while **preserving all other bits**:

~~~java
flags &= ~WRITE;
~~~

Example:

~~~text
flags        = 0111   (READ | WRITE | EXECUTE)
WRITE        = 0010
~WRITE (4bit)= 1101
AND          = 0101   (READ | EXECUTE)
~~~

In actual Java execution, `~WRITE` is a 32-bit `int` operation, not just a 4-bit inversion. Still, `flags & ~WRITE` works correctly because the WRITE bit becomes 0 while all other bit positions in `~WRITE` are 1, preserving those bits.

~~~java
int flags = READ | WRITE | EXECUTE;
flags &= ~WRITE;
System.out.println(flags); // 5
~~~

Clearing multiple flags at once:

~~~java
flags &= ~(READ | EXECUTE);
~~~

**Idempotence:** clearing a flag that is already cleared leaves the value unchanged.

**Do not use `flags &= WRITE` when trying to clear WRITE:** that operation **keeps only** the WRITE bit and clears all other bits. To remove WRITE, you must use `~WRITE`.

## 7. Toggling Flags with XOR

XOR flips the state of every bit in `mask`:

- 0 becomes 1.
- 1 becomes 0.

~~~java
int flags = READ; // 0001
flags ^= EXECUTE; // 0101: turn EXECUTE on
flags ^= EXECUTE; // 0001: turn EXECUTE off
~~~

Meaning table:

| Initial state of a bit | OR with 1 | AND with 0 | XOR with 1 |
|---|---|---|---|
| 0 (off) | On (1) | Off (0) | On (1) |
| 1 (on) | Stays on (1) | Off (0) | Off (0) |

XOR is **not idempotent** for bits in the mask: applying it twice returns to the initial state.

~~~java
int state = 0;
state ^= READ;
state ^= READ;
System.out.println(state); // 0
~~~

**Do not use XOR to "ensure a flag is enabled"**, because if the flag is already on, XOR will turn it off.

## 8. Illustrative Flag Management Flow

~~~mermaid
flowchart TD
    A["Start: flags = 0000"] --> B["flags |= READ | WRITE"]
    B --> C["0011: READ and WRITE set"]
    C --> D["flags &= ~WRITE"]
    D --> E["0001: only READ set"]
    E --> F["flags ^= EXECUTE"]
    F --> G["0101: READ and EXECUTE set"]
    G --> H["flags ^= EXECUTE"]
    H --> I["0001: EXECUTE cleared again"]
~~~

This is **bitmask manipulation on an integer variable**, not a complete real-world authorization system by itself. If flags represent actual access permissions, authentication, authorization checks, trusted input handling, and state synchronization must still be designed separately.

## 9. Defining Flag Positions Using `1 << position`

Instead of writing magic numbers:

~~~java
static final int READ    = 1 << 0;
static final int WRITE   = 1 << 1;
static final int EXECUTE = 1 << 2;
static final int ADMIN   = 1 << 3;
~~~

For `int`, valid bit positions are **0 to 31**; for `long`, positions are **0 to 63**:

~~~java
int highestIntBit = 1 << 31;
long highLongBit = 1L << 40;
~~~

**Two warnings:**

1. `1 << 31` equals `Integer.MIN_VALUE`, which is a **negative** number because the sign bit is set. It is still a valid bit mask. Test it with `(flags & highestIntBit) != 0`, **never `> 0`**, because AND can return a negative value.
2. `int` shift distances use only the **low 5 bits**, and `long` uses the **low 6 bits**. `1 << 32` actually evaluates as `1 << 0` → 1, easily causing **flag collisions**. You must use `1L << 32` to create bit 32 in a `long`.

If `position` comes from dynamic data, explicitly validate `0 <= position && position < 32` (or `< 64` for `long`); Java will not throw an error if you shift out of range.

## 10. `~` Inverts the Entire Width: Remember to Bound the Target Bit Region

~~~java
int flag = READ; // 0001
System.out.println(~flag); // -2
~~~

`~1` on `int` is not simply `1110`; it inverts **all 32 bits**, becoming `0xFFFFFFFE` or -2.

If you only care about the **low 4 bits**, mask it again:

~~~java
int FOUR_BITS = 0b1111;
int invertedWithin4Bits = (~READ) & FOUR_BITS;
System.out.println(invertedWithin4Bits); // 14 = 1110
~~~

**Do not be misled:** `~mask` by itself produces a value with high bits set to 1; that is normal inside `flags & ~mask` when the goal is to **preserve all other bits**. Only restrict it with `& allowedBits` when you want a standalone result constrained to a specific bit region.

## 11. `byte`, the Sign Bit, and Reading 8 Unsigned Bits

Bitwise operations on `byte`, `short`, and `char` generally **promote operands to `int`** before computing. A negative `byte` is sign-extended when widened to `int`.

~~~java
byte encoded = (byte) 0b1111_0000;
System.out.println(encoded);         // -16
System.out.println(encoded & 0xFF);  // 240
~~~

- As a signed `byte`, bits `11110000` represent -16.
- `encoded & 0xFF` retains only the low 8 bits, returning an `int` equal to 240 (interpreting the byte as unsigned).

With `byte`, compound assignments such as `byteVar |= mask` can **implicitly narrow** the `int` result back to `byte`. If you are handling 8-bit flags and want non-negative values 128–255, work in `int` after masking with `& 0xFF`, or use another data model with explicit bounds checking.

## 12. Writing Clear Helper Methods and Validating Masks

A small set of helper methods avoids repeating formulas and confusing **any** with **all**:

~~~java
static boolean hasAny(int flags, int mask) {
    return (flags & mask) != 0;
}
static boolean hasAll(int flags, int mask) {
    return (flags & mask) == mask;
}
static int enable(int flags, int mask) {
    return flags | mask;
}
static int disable(int flags, int mask) {
    return flags & ~mask;
}
static int toggle(int flags, int mask) {
    return flags ^ mask;
}
~~~

These helpers **do not mutate the caller's variable** (Java passes `int` by value); they return the new state after enabling/disabling/toggling. Callers must assign the return value back if they want to update their variable:

~~~java
flags = enable(flags, READ);
~~~

For APIs with a valid flag set `allowed`, **reject masks that are 0 or contain unknown bits**:

~~~java
static void requireValidMask(int mask, int allowed) {
    if (mask == 0 || (mask & ~allowed) != 0) {
        throw new IllegalArgumentException("invalid flag mask");
    }
}
~~~

- `mask == 0`: prevents an "all" check from returning true vacuously.
- `(mask & ~allowed) != 0`: detects **at least one bit outside the allowed set**.
- This method does not prove a user has permission to enable flags; it only **validates the shape of the mask**.

## 13. Common Pitfalls

| Misconception | Consequence | Correct approach |
|---|---|---|
| Checking multiple flags with `(flags & mask) != 0` and treating it as "all present" | Returns true if even one bit is set | Use `(flags & mask) == mask` |
| Treating `hasAll(flags, 0)` as meaning permissions were granted | Vacuously true result | Forbid mask 0 if invalid |
| Clearing a flag with `flags &= mask` | Clears all other bits and keeps only `mask` | `flags &= ~mask` |
| Setting a flag with `flags ^= mask` | Can turn off a flag that was already on | `flags |= mask` |
| Writing `flags & mask > 0` | Operator precedence and sign-bit bugs | `(flags & mask) != 0` |
| Thinking `~READ` inverts only 4 bits | `~` inverts all 32 bits of `int` | `(~READ) & 0b1111` when 4 bits are wanted |
| Thinking `1 << 31` is invalid because it is negative | The sign bit can be used as a flag | Check `!= 0`, never `> 0` |
| Thinking `1 << 32` creates bit 32 | `int` shifts mask 5 bits; becomes bit 0 | Use `1L << 32` or validate position |
| Assuming a `byte` storing `0xF0` equals 240 | Signed `byte` returns -16 | `byteValue & 0xFF` to read unsigned |
| Using `&&` between two `int` values | Won't compile: `&&` requires booleans | Use bitwise `&`, then compare with 0 |
| Thinking `flags |= mask` is automatically thread-safe | Read–modify–write is not atomic | Synchronize or use `AtomicInteger` if shared across threads |
| Treating a bitmask as a complete security authorization system | A bitmask only represents state | Enforce permission checks on a trusted boundary |

## 14. Complete Java 17 Program

Save the file with the exact name **`BitMaskFlagsDemo.java`**:

~~~java
public final class BitMaskFlagsDemo {
    private BitMaskFlagsDemo() {}

    static final int READ = 1 << 0;
    static final int WRITE = 1 << 1;
    static final int EXECUTE = 1 << 2;
    static final int ADMIN = 1 << 3;
    static final int ALL_ALLOWED = READ | WRITE | EXECUTE | ADMIN;

    static boolean hasAny(int flags, int mask) {
        return (flags & mask) != 0;
    }

    static boolean hasAll(int flags, int mask) {
        return (flags & mask) == mask;
    }

    static int enable(int flags, int mask) {
        return flags | mask;
    }

    static int disable(int flags, int mask) {
        return flags & ~mask;
    }

    static int toggle(int flags, int mask) {
        return flags ^ mask;
    }

    static void requireValidMask(int mask, int allowed) {
        if (mask == 0 || (mask & ~allowed) != 0) {
            throw new IllegalArgumentException("invalid flag mask");
        }
    }

    public static void main(String[] args) {
        int flags = 0;
        System.out.println("initial=" + flags);

        flags = enable(flags, READ | WRITE);
        System.out.println("enabled READ|WRITE=" + flags);
        System.out.println("has READ=" + hasAny(flags, READ));
        System.out.println("has EXECUTE=" + hasAny(flags, EXECUTE));
        System.out.println("has both READ|WRITE="
                + hasAll(flags, READ | WRITE));
        System.out.println("has both READ|EXECUTE="
                + hasAll(flags, READ | EXECUTE));
        System.out.println("has any WRITE|EXECUTE="
                + hasAny(flags, WRITE | EXECUTE));

        flags = disable(flags, WRITE);
        System.out.println("disabled WRITE=" + flags);

        flags = toggle(flags, EXECUTE);
        System.out.println("toggle EXECUTE on=" + flags);
        flags = toggle(flags, EXECUTE);
        System.out.println("toggle EXECUTE off=" + flags);

        flags = enable(flags, ADMIN);
        System.out.println("enabled ADMIN=" + flags);
        flags = disable(flags, READ | ADMIN);
        System.out.println("cleared READ|ADMIN=" + flags);

        System.out.println("all with zero mask=" + hasAll(flags, 0));
        System.out.println("any with zero mask=" + hasAny(flags, 0));

        flags = enable(flags, READ | EXECUTE);
        System.out.println("current binary="
                + Integer.toBinaryString(flags));
        System.out.println("allowed binary="
                + Integer.toBinaryString(ALL_ALLOWED));
        System.out.println("~READ raw=" + (~READ));
        System.out.println("~READ within four bits="
                + ((~READ) & ALL_ALLOWED));

        byte encoded = (byte) 0b1111_0000;
        System.out.println("byte signed=" + encoded);
        System.out.println("byte unsigned=" + (encoded & 0xFF));

        int highBit = 1 << 31;
        int withHigh = highBit;
        System.out.println("high bit flag=" + withHigh);
        System.out.println("high bit detected="
                + hasAny(withHigh, highBit));
        System.out.println("high bit unsigned="
                + Integer.toUnsignedLong(withHigh));

        System.out.println("1 << 32=" + (1 << 32));
        System.out.println("1L << 32=" + (1L << 32));

        requireValidMask(READ | WRITE, ALL_ALLOWED);
        System.out.println("valid mask=accepted");
        try {
            requireValidMask(0, ALL_ALLOWED);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero mask=" + ex.getMessage());
        }
        try {
            requireValidMask(1 << 4, ALL_ALLOWED);
        } catch (IllegalArgumentException ex) {
            System.out.println("unknown mask=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later; open a terminal in the directory containing `BitMaskFlagsDemo.java`. The program uses no libraries outside the JDK and requires no Maven/Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BitMaskFlagsDemo.java
java -cp . BitMaskFlagsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BitMaskFlagsDemo.java
java -cp . BitMaskFlagsDemo
~~~

### Exact expected stdout

~~~text
initial=0
enabled READ|WRITE=3
has READ=true
has EXECUTE=false
has both READ|WRITE=true
has both READ|EXECUTE=false
has any WRITE|EXECUTE=true
disabled WRITE=1
toggle EXECUTE on=5
toggle EXECUTE off=1
enabled ADMIN=9
cleared READ|ADMIN=0
all with zero mask=true
any with zero mask=false
current binary=101
allowed binary=1111
~READ raw=-2
~READ within four bits=14
byte signed=-16
byte unsigned=240
high bit flag=-2147483648
high bit detected=true
high bit unsigned=2147483648
1 << 32=1
1L << 32=4294967296
valid mask=accepted
zero mask=invalid flag mask
unknown mask=invalid flag mask
~~~

### Explaining Each Output Group

1. **Set:** `READ|WRITE = 3`; after disabling WRITE, 1 remains.
2. **Read:** `hasAny(3, WRITE|EXECUTE)` is true because WRITE is set, whereas `hasAll(3, READ|EXECUTE)` is false because EXECUTE is off.
3. **Toggle:** XOR with EXECUTE twice cycles `1 → 5 → 1`.
4. **Clear multiple:** removing READ and ADMIN when flags is 9 resets flags to 0.
5. **Empty mask:** `hasAll(0,0)` is true under the mask comparison; `hasAny(0,0)` is false.
6. **Representation:** `flags = 5` is `101` in binary; `ALL_ALLOWED = 15` is `1111`.
7. **NOT:** `~1` is -2 because all 32 bits are inverted; masking to 4 bits yields 14.
8. **Byte:** bit pattern `11110000` is -16 as a signed `byte`, and 240 after `& 0xFF`.
9. **Sign bit:** mask `1 << 31` has a negative `int` value; testing `!= 0` still works accurately.
10. **Shift distance:** `1 << 32` wraps back to bit 0 for `int`, while `1L << 32` creates bit 32 on `long`.
11. **Validation:** masks within the allowed set are accepted; a zero mask or one with unknown bits is rejected.

## 15. Exercises with Answers

### Exercise A — Setting and Checking Two Flags

~~~java
int flags = 0;
flags |= READ | EXECUTE;
System.out.println((flags & READ) != 0);
System.out.println((flags & WRITE) != 0);
~~~

**Answer:**

~~~text
true
false
~~~

### Exercise B — "Any" vs. "All"

~~~java
int flags = READ | WRITE;
int mask = READ | EXECUTE;

System.out.println((flags & mask) != 0);
System.out.println((flags & mask) == mask);
~~~

**Answer:**

~~~text
true
false
~~~

### Exercise C — Clearing One Flag, Keeping the Rest

~~~java
int flags = READ | WRITE | EXECUTE;
flags &= ~WRITE;
System.out.println(flags);
~~~

**Answer:** `5`, containing READ and EXECUTE.

### Exercise D — Toggling Twice

~~~java
int flags = READ;
flags ^= ADMIN;
flags ^= ADMIN;
System.out.println(flags);
~~~

**Answer:** `1`. XORing twice with the same mask restores the initial state.

### Exercise E — Highest Mask Bit of `int`

~~~java
int highest = 1 << 31;
System.out.println(highest);
System.out.println((highest & highest) != 0);
System.out.println((highest & highest) > 0);
~~~

**Answer:**

~~~text
-2147483648
true
false
~~~

The sign-bit flag is still set, so **never use `> 0` to test a bitmask**.

### Exercise F — Zero Mask and Invalid Bit Position

Why is `hasAll(flags, 0)` always true? Why does `1 << 32` not represent bit 32 of an `int`?

**Answer:** `flags & 0` is always 0, so comparing it with mask 0 returns true. For 32-bit `int`, Java uses only the low 5 bits of the shift count: `32 & 31 = 0`, so `1 << 32` equals `1 << 0`. You must validate masks and bit positions against valid bounds.

## 16. Checklist and Conclusion

- [ ] Know how to define individual flags using `1 << position` or `1L << position`.
- [ ] Know how to combine flags using OR `|`.
- [ ] Know how to check a single flag / at least one flag using `(flags & mask) != 0`.
- [ ] Know how to verify all flags are present using `(flags & mask) == mask`.
- [ ] Know how to set with `flags |= mask`, clear with `flags &= ~mask`, and toggle with `flags ^= mask`.
- [ ] Understand that OR-setting and AND-NOT-clearing are idempotent, whereas XOR toggles on every call.
- [ ] Do not confuse bitwise `~` with boolean `!`.
- [ ] Understand that `~` inverts every bit of `int`/`long`; apply an extra mask when you need only a low bit region.
- [ ] Know the vacuous `hasAll(flags, 0)` true case and why empty masks must be validated.
- [ ] Recognize the sign bit `1 << 31` and test only with `!= 0`, never `> 0`.
- [ ] Understand signed `byte` and `& 0xFF` to interpret 8 bits as unsigned.
- [ ] Validate bit positions: 0–31 for `int`, 0–63 for `long`.
- [ ] Do not mistake bitmasks for a full security or thread-safety solution.
- [ ] Compile and run `BitMaskFlagsDemo.java` on Java 17+ and verify exact stdout.

**Conclusion:** Bit masks allow storing multiple independent flags in a single integer variable. Remember the four rules: **read with `&`**, **set with `|`**, **clear with `& ~`**, and **toggle with `^`**. When implementing them, distinguish *any/all* checks, guard against zero masks and invalid bits, account for sign bits and integer widths, and keep your business intent clear.
